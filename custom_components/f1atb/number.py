"""F1ATB numbers, per action:
- Max opening in auto routing (Vmax, %).
- Forced-on opening (ForceOuvre, %): opening applied while the routing is forced on.
- Appliance max power (W): HA-side calibration (100 % opening = this power).
- Forced-on power (W): enter a power → the opening is computed (power / max power × 100),
  written, and the routing is forced on. 0 → back to auto.
"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_FORCE_MINUTES, DEFAULT_FORCE_MINUTES, DOMAIN
from .entity import F1atbActionEntity
from .helpers import async_setup_action_platform

DEFAULT_MAX_POWER = 3000.0  # W at 100 % opening (starting value, editable)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    def factory(index: int) -> list:
        return [
            ForcedOpeningNumber(coordinator, index),
            MaxPowerNumber(coordinator, index),
            ForcedPowerNumber(coordinator, index, entry),
            AutoMaxOpeningNumber(coordinator, index),
        ]

    async_setup_action_platform(entry, coordinator, async_add_entities, factory)


class AutoMaxOpeningNumber(F1atbActionEntity, NumberEntity):
    """MAX opening in AUTO routing = Vmax of the periods. Written with /ParaNew.

    Not to be confused with the forced-on opening (ForceOuvre): this is the ceiling the normal
    algorithm never exceeds. Applied to ALL periods. Meaningful for proportional modes
    (triac / SSR: phase cut, half-sine, PWM…). For a relay in On/Off mode the firmware uses
    Vmax as a power-off threshold in WATTS, so the entity is unavailable there.
    """

    _attr_icon = "mdi:arrow-collapse-vertical"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _kind = "auto_ouverture_max"
    _name_key = "auto_max_opening"

    def __init__(self, coordinator, index: int) -> None:
        super().__init__(coordinator, index)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_auto_ouverture_max_{index}"

    @property
    def available(self) -> bool:
        a = self._action
        relay_on_off = bool(a) and a.get("mode") == 1 and not a.get("is_triac")
        # Vmax comes from /ParaFixe: unavailable until the config is read.
        return super().available and self._config_ok and not relay_on_off

    @property
    def native_value(self) -> float | None:
        a = self._action
        return None if a is None else float(a.get("auto_ouvre_max", 100) or 0)

    async def async_set_native_value(self, value: float) -> None:
        idx = self._index
        v = int(max(0, min(100, value)))

        def _mutate(config: dict) -> None:
            actions = config.get("Actions") or []
            if 0 <= idx < len(actions):
                periods = actions[idx].get("Periodes")
                if periods is None:
                    periods = actions[idx].get("Périodes")
                for p in (periods or []):
                    p["Vmax"] = v  # same ceiling on every period

        await self.coordinator.client.async_patch_config(_mutate)
        await self._write_and_refresh(config_change=True)


class ForcedOpeningNumber(F1atbActionEntity, NumberEntity):
    """Opening applied while FORCED ON (ForceOuvre field). Written with /ParaNew (persistent).

    Not to be confused with the auto max opening: this is the opening used when the routing
    is forced on, not the ceiling of the automatic routing.
    """

    _attr_icon = "mdi:gauge"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _kind = "ouverture_max"
    _name_key = "forced_opening"

    def __init__(self, coordinator, index: int) -> None:
        super().__init__(coordinator, index)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_ouverture_max_{index}"

    @property
    def available(self) -> bool:
        # ForceOuvre comes from /ParaFixe: unavailable until the config is read.
        return super().available and self._config_ok

    @property
    def native_value(self) -> float | None:
        a = self._action
        return None if a is None else float(a.get("force_ouvre", 0) or 0)

    async def async_set_native_value(self, value: float) -> None:
        idx = self._index
        v = int(max(0, min(100, value)))

        def _mutate(config: dict) -> None:
            actions = config.get("Actions") or []
            if 0 <= idx < len(actions):
                actions[idx]["ForceOuvre"] = v

        await self.coordinator.client.async_patch_config(_mutate)
        await self._write_and_refresh(config_change=True)


class MaxPowerNumber(F1atbActionEntity, RestoreNumber):
    """Calibration: power drawn by the appliance at 100 % opening (W).

    Stored on the Home Assistant side (the firmware has no such setting). Used to compute the
    opening of the forced-on power. Kept across restarts.
    """

    _attr_icon = "mdi:flash-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = 10000
    _attr_native_step = 50
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _kind = "puissance_max"
    _name_key = "max_power"

    def __init__(self, coordinator, index: int) -> None:
        super().__init__(coordinator, index)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_puissance_max_{index}"
        coordinator.appliance_max_power.setdefault(index, DEFAULT_MAX_POWER)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Restore the stored value (otherwise keep the one already in the coordinator, which
        # survives an inactive→active cycle within the same HA session).
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self.coordinator.appliance_max_power[self._index] = float(last.native_value)

    @property
    def native_value(self) -> float | None:
        # Single source of truth = the coordinator, so the automatic calibration (which writes
        # into this dict) updates the display by itself.
        return float(self.coordinator.appliance_max_power.get(self._index, DEFAULT_MAX_POWER))

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **super().extra_state_attributes,
            "calibrating": self.coordinator.is_calibrating(self._index),
        }

    async def async_set_native_value(self, value: float) -> None:
        # MANUAL entry: always allowed (overrides the automatic calibration).
        self.coordinator.appliance_max_power[self._index] = float(max(0, value))
        self.async_write_ha_state()


class ForcedPowerNumber(F1atbActionEntity, RestoreNumber):
    """Forced-on power (W): enter the power to route.

    The opening = power / max power × 100 is computed, written to ForceOuvre (/ParaNew) and
    the routing is forced on (/ForceAction). 0 → back to auto.
    """

    _attr_icon = "mdi:flash"
    _attr_native_min_value = 0
    # FIXED, generous ceiling: do NOT set it to the max power, otherwise HA rejects any value
    # above it (ServiceValidationError) before async_set_native_value is even called. The real
    # cap (route at most 100 %) is the opening clamp below; the card limits input to max power.
    _attr_native_max_value = 10000
    _attr_native_step = 50
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _kind = "marche_forcee_w"
    _name_key = "forced_power"

    def __init__(self, coordinator, index: int, entry: ConfigEntry) -> None:
        super().__init__(coordinator, index)
        self._entry = entry
        self._attr_unique_id = f"{coordinator.entry.unique_id}_marche_forcee_w_{index}"
        self._value = 0.0

    def _max_power(self) -> float:
        return float(self.coordinator.appliance_max_power.get(self._index, DEFAULT_MAX_POWER)) or DEFAULT_MAX_POWER

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._value = float(last.native_value)

    @property
    def native_value(self) -> float | None:
        return self._value

    @property
    def extra_state_attributes(self) -> dict:
        pmax = self._max_power()
        opening = int(max(0, min(100, round(self._value / pmax * 100)))) if pmax else 0
        return {
            **super().extra_state_attributes,
            "puissance_max": pmax,
            "ouverture_calculee": opening,
        }

    async def async_set_native_value(self, value: float) -> None:
        idx = self._index
        value = float(max(0, value))
        self._value = value
        minutes = int(self._entry.options.get(CONF_FORCE_MINUTES, DEFAULT_FORCE_MINUTES))

        if value <= 0:
            # Back to auto (end of the forced-on)
            await self.coordinator.client.async_force_action(idx, 0)
            await self._write_and_refresh(config_change=False)
            self.async_write_ha_state()
            return

        pmax = self._max_power()
        opening = int(max(0, min(100, round(value / pmax * 100))))

        def _mutate(config: dict) -> None:
            actions = config.get("Actions") or []
            if 0 <= idx < len(actions):
                actions[idx]["ForceOuvre"] = opening

        await self.coordinator.client.async_patch_config(_mutate)
        await self.coordinator.client.async_force_action(idx, minutes)  # forced on
        await self._write_and_refresh(config_change=True)
        self.async_write_ha_state()
