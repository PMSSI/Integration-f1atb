"""F1ATB data update coordinator.

- LIVE data (powers, energies, active actions, system info): every cycle.
- CONFIG (/ParaFixe: waveform `Actif`, `ForceOuvre`, `Vmax`): refreshed periodically (also picks
  up changes made in the router's web UI) and right after a write.
The mode and ForceOuvre are merged into each live action to keep the entities simple.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import F1atbApiError, F1atbClient
from .const import (
    CONF_LANGUAGE,
    CONF_TANK_SETPOINT,
    CONF_TANK_VOLUME,
    DEFAULT_TANK_SETPOINT,
    DEFAULT_TANK_VOLUME,
    DOMAIN,
    FAILURES_BEFORE_OFFLINE,
    LANGUAGE_AUTO,
)
from .i18n import resolve_language, tr
from .water_heater import FULL_OPENING_MIN, TankModel

_LOGGER = logging.getLogger(__name__)

CONFIG_EVERY = 6  # refresh the config every N cycles (~30 s at a 5 s interval)

# --- Automatic calibration of the appliance max power ---
CALIB_FORCE_MINUTES = 2   # short forced-on = safety net if going back to auto fails
CALIB_SETTLE_S = 5        # time for the measurement to settle after opening to 100 %
CALIB_SAMPLES = 5         # number of routed-power samples…
CALIB_INTERVAL_S = 2      # …taken every N s (≈ 10 s average)


class F1atbCoordinator(DataUpdateCoordinator[dict]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: F1atbClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="F1ATB Solar Router",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.entry = entry
        self.config: dict = {}
        self.language = resolve_language(
            entry.options.get(CONF_LANGUAGE, LANGUAGE_AUTO), hass.config.language
        )
        # HA-side calibration (the firmware has no such setting): power drawn by the appliance
        # at 100 % opening, per action. Used by the "forced-on power (W)" mode.
        self.appliance_max_power: dict[int, float] = {}
        self._calibrating: set[int] = set()
        self._config_countdown = 0
        self._failures = 0
        # Optional hot-water tank model, stepped every minute (also while the router is off).
        volume = float(entry.options.get(CONF_TANK_VOLUME, DEFAULT_TANK_VOLUME) or 0)
        self.tank: TankModel | None = (
            TankModel(volume, float(entry.options.get(CONF_TANK_SETPOINT, DEFAULT_TANK_SETPOINT)))
            if volume > 0 else None
        )
        self._tank_store: Store[dict] = Store(hass, 1, f"{DOMAIN}.tank.{entry.entry_id}")
        self._tank_meter: float | None = None  # last lifetime meter reading (Wh)

    def tr(self, key: str, **kwargs) -> str:
        return tr(self.language, key, **kwargs)

    # ------------------------------------------------------------------ hot-water tank
    @property
    def tank_signal(self) -> str:
        return f"{DOMAIN}_tank_{self.entry.entry_id}"

    async def async_tank_load(self) -> None:
        if self.tank is None:
            return
        stored = await self._tank_store.async_load()
        if stored:
            try:
                self.tank.restore(stored)
            except (TypeError, ValueError) as err:
                _LOGGER.warning("Tank model state not restored: %s", err)
            # Home Assistant was stopped meanwhile: catch up with losses and draws only (the
            # heating during the gap is unknown; the next full tank re-anchors the model).
            self.tank.step(dt_util.now(), 0.0, False)

    async def async_tank_save(self) -> None:
        if self.tank is not None:
            await self._tank_store.async_save(self.tank.to_dict())

    @callback
    def async_tank_tick(self, _now=None) -> None:
        """Advance the tank model by one step (every minute)."""
        if self.tank is None:
            return
        data = self.data or {}
        online = bool(self.last_update_success and data)
        power = float(data.get("routed_power") or 0.0) if online else 0.0
        openings = [a.get("opening") or 0 for a in (data.get("actions") or {}).values()]
        wants = online and bool(openings) and max(openings) >= FULL_OPENING_MIN

        # Energy actually delivered since the last step, from the lifetime meter; rejected when
        # implausible (router reboot glitch, more than 4 kW on average) → fall back to the power.
        energy_wh = None
        meter = data.get("routed_energy_total") if online else None
        now = dt_util.now()
        if meter is not None and self._tank_meter is not None and self.tank.last_update:
            delta = meter - self._tank_meter
            hours = (now - self.tank.last_update).total_seconds() / 3600
            if hours > 0 and 0 <= delta <= 4000 * hours:
                energy_wh = delta
        self._tank_meter = meter if meter is not None else self._tank_meter
        if not online:
            self._tank_meter = None  # power is 0 while offline; restart the meter delta on return

        if self.tank.step(now, power, wants, energy_wh):
            _LOGGER.debug("Hot-water tank full (thermostat cut detected), usage %.1f L/day",
                          self.tank.usage_l_day)
        self._tank_store.async_delay_save(self.tank.to_dict, 300)
        # Only the tank entities are refreshed (not every coordinator listener).
        async_dispatcher_send(self.hass, self.tank_signal)

    def tank_set_percent(self, percent: float) -> None:
        if self.tank is not None:
            self.tank.set_percent(dt_util.now(), percent)
            self._tank_store.async_delay_save(self.tank.to_dict, 5)
            async_dispatcher_send(self.hass, self.tank_signal)

    def is_calibrating(self, index: int) -> bool:
        return index in self._calibrating

    async def async_calibrate(self, index: int) -> None:
        """Calibrate the max power: open to 100 %, let the measurement settle, average the
        routed power over ~10 s, store the result, then go back to auto.

        Safety: short forced-on (CALIB_FORCE_MINUTES), back to auto in a `finally` that cannot
        fail, and the user's forced-on opening (ForceOuvre) is restored afterwards.
        """
        if index in self._calibrating:
            return
        self._calibrating.add(index)
        self.async_update_listeners()  # show "calibrating" in the UI
        original: dict[str, int] = {}
        try:
            def _open_fully(config: dict) -> None:
                actions = config.get("Actions") or []
                if 0 <= index < len(actions):
                    original["ForceOuvre"] = actions[index].get("ForceOuvre", 100)
                    actions[index]["ForceOuvre"] = 100

            await self.client.async_patch_config(_open_fully)
            await self.client.async_force_action(index, CALIB_FORCE_MINUTES)
            await self.async_refresh_config()

            await asyncio.sleep(CALIB_SETTLE_S)

            samples: list[float] = []
            for _ in range(CALIB_SAMPLES):
                await self.async_request_refresh()
                p = (self.data or {}).get("routed_power")
                try:
                    p = float(p)
                except (TypeError, ValueError):
                    p = None
                if p is not None and p > 0:
                    samples.append(p)
                await asyncio.sleep(CALIB_INTERVAL_S)

            act = (self.data or {}).get("actions", {}).get(index, {})
            name = act.get("name") or self.tr("action", index=index)
            notif_id = f"f1atb_calib_{index}"
            if samples:
                avg = sum(samples) / len(samples)
                self.appliance_max_power[index] = round(avg)
                _LOGGER.info("Calibration of %s: %d W (average of %d samples)", name, round(avg), len(samples))
                persistent_notification.async_dismiss(self.hass, notif_id)
            else:
                # No routed power measured: the appliance did not draw power (e.g. water heater
                # already hot, thermostat open). The max power is NOT changed.
                _LOGGER.warning("Calibration of %s: no power measured (appliance already hot?)", name)
                persistent_notification.async_create(
                    self.hass,
                    self.tr("calib_message", action=name),
                    title=self.tr("calib_title"),
                    notification_id=notif_id,
                )
        finally:
            self._calibrating.discard(index)
            try:
                await self.client.async_force_action(index, 0)  # back to auto
                if "ForceOuvre" in original:
                    value = original["ForceOuvre"]

                    def _restore(config: dict) -> None:
                        actions = config.get("Actions") or []
                        if 0 <= index < len(actions):
                            actions[index]["ForceOuvre"] = value

                    await self.client.async_patch_config(_restore)
            except F1atbApiError as err:
                # Router unreachable (e.g. switched off): the 2-minute forced-on expires by itself.
                _LOGGER.warning("Calibration cleanup failed for action %s: %s", index, err)
            await self.async_refresh_config()
            await self.async_request_refresh()
            self.async_update_listeners()

    async def async_refresh_config(self) -> None:
        """Re-read the full config (after a write, so the change shows up)."""
        try:
            self.config = await self.client.async_get_config()
            self._config_countdown = CONFIG_EVERY
        except F1atbApiError as err:
            _LOGGER.debug("Config refresh failed: %s", err)

    async def _async_update_data(self) -> dict:
        try:
            data = await self.client.async_get_data()
        except F1atbApiError as err:
            self._failures += 1
            # A single missed poll (busy ESP32, Wi-Fi blip) must not make every entity
            # unavailable: keep the last data for a few cycles before reporting offline.
            if self.data is not None and self._failures < FAILURES_BEFORE_OFFLINE:
                _LOGGER.debug("Poll failed (%s), keeping last data (%d/%d)",
                              err, self._failures, FAILURES_BEFORE_OFFLINE)
                return self.data
            raise UpdateFailed(str(err)) from err
        self._failures = 0

        # `not self.config`: back from a start while the router was off, the config is empty →
        # read it right away. The countdown is only re-armed on SUCCESS, otherwise we would retry
        # only 6 cycles later (entities stuck with mode/opening 0).
        if self._config_countdown <= 0 or not self.config:
            try:
                self.config = await self.client.async_get_config()
                self._config_countdown = CONFIG_EVERY
            except F1atbApiError as err:
                _LOGGER.debug("Config not refreshed: %s", err)
        self._config_countdown -= 1

        # Merge mode (Actif) + ForceOuvre + auto max opening (Vmax) into each active action
        cfg_actions = self.config.get("Actions") or []
        for idx, a in (data.get("actions") or {}).items():
            cfg = cfg_actions[idx] if 0 <= idx < len(cfg_actions) else {}
            a["mode"] = int(cfg.get("Actif", 0) or 0)
            a["force_ouvre"] = int(cfg.get("ForceOuvre", 0) or 0)
            a["is_triac"] = idx == 0
            periods = cfg.get("Periodes") or cfg.get("Périodes") or []
            a["auto_ouvre_max"] = int(periods[0].get("Vmax", 100) or 0) if periods else 100
            # Without config (router just booted, /ParaFixe not read yet) mode/ForceOuvre are 0:
            # the entities depending on them stay UNAVAILABLE instead of confidently showing
            # "Inactive / opening 0".
            a["config_ok"] = bool(cfg)

        # Actions enabled in the config (Actif != 0), None while the config is unknown. An action
        # missing from /ajax_etatActions but still enabled (e.g. triac without zero-cross signal)
        # keeps its entities, shown as unavailable.
        data["configured_actions"] = (
            {i for i, cfg in enumerate(cfg_actions) if int((cfg or {}).get("Actif", 0) or 0) != 0}
            if self.config else None
        )

        # Temperature channels (0..3): configured in /ParaFixe (Source_Temp != "tempNo"),
        # name = nomTemperature{c}, value from /ajax_data (None when the probe is missing / -127).
        temps = data.get("temperatures") or []
        tchan: dict[int, dict] = {}
        if self.config:  # without config we don't know which channels exist → create nothing
            for c in range(4):
                src = self.config.get(f"Source_Temp{c}")
                val = temps[c] if c < len(temps) else None
                configured = src not in (None, "", "tempNo")
                # include if configured, or (config read but without these keys) if a value is there
                if configured or (src is None and val is not None):
                    name = (self.config.get(f"nomTemperature{c}") or "").strip() or self.tr(
                        "temperature", channel=c
                    )
                    tchan[c] = {"name": name, "source": src or "?", "value": val}
        data["temp_channels"] = tchan
        return data
