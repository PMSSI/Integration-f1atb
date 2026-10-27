"""F1ATB sensors: routing powers and energies (global) + opening % (per active action)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import F1atbActionEntity, F1atbBaseEntity
from .filters import monotonic_total
from .helpers import (
    async_setup_action_platform,
    temp_channel_indices,
    temp_channel_retained,
)
from .water_heater import cold_water_temp

# Beyond this gap between two samples (HA restart, router switched off) the interval is not
# integrated: the period is skipped instead of inventing energy.
INTEGRATION_MAX_DT = 600  # seconds


@dataclass(frozen=True, kw_only=True)
class F1atbSensorDesc(SensorEntityDescription):
    value: Callable[[dict], float | None]


GLOBAL_SENSORS: tuple[F1atbSensorDesc, ...] = (
    F1atbSensorDesc(
        key="grid_import_power",
        icon="mdi:transmission-tower-export",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.get("grid_import_power"),
    ),
    F1atbSensorDesc(
        key="grid_export_power",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.get("grid_export_power"),
    ),
    F1atbSensorDesc(
        key="routed_power",
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.get("routed_power"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list = [F1atbGlobalSensor(coordinator, desc) for desc in GLOBAL_SENSORS]
    entities.append(F1atbRoutedTotalSensor(coordinator))
    entities.append(F1atbRoutedTodaySensor(coordinator))
    if coordinator.tank is not None:
        entities += [
            TankChargeSensor(coordinator),
            TankEnergySensor(coordinator),
            TankHotWaterSensor(coordinator),
        ]
    async_add_entities(entities)

    # Opening % per active action (dynamic)
    def factory(index: int) -> list:
        return [OpeningSensor(coordinator, index)]

    async_setup_action_platform(entry, coordinator, async_add_entities, factory)

    # Temperature of the configured channels 0..3 (dynamic)
    def temp_factory(channel: int) -> list:
        return [TemperatureSensor(coordinator, channel)]

    async_setup_action_platform(
        entry,
        coordinator,
        async_add_entities,
        temp_factory,
        keys_fn=temp_channel_indices,
        retained_fn=temp_channel_retained,
    )


class F1atbGlobalSensor(F1atbBaseEntity, SensorEntity):
    entity_description: F1atbSensorDesc

    def __init__(self, coordinator, description: F1atbSensorDesc) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"

    @property
    def name(self) -> str:
        return self.coordinator.tr(self.entity_description.key)

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict:
        return {"f1atb_kind": self.entity_description.key}


class F1atbRoutedTotalSensor(F1atbBaseEntity, RestoreSensor):
    """Lifetime routed energy (meter counter): the sensor to use in the Energy dashboard.

    Filtered so it never goes backwards: at boot the firmware briefly reports a stale midnight
    snapshot or 0, which the recorder would take as a meter reset and then count the whole
    lifetime total again. The last good value survives HA restarts.
    """

    _attr_icon = "mdi:lightning-bolt-outline"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_routed_energy_total"
        self._value: float | None = None
        self._drop_since: float | None = None

    @property
    def name(self) -> str:
        return self.coordinator.tr("routed_energy_total")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._value = float(last.native_value)
            except (TypeError, ValueError):
                self._value = None
        self._update_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_value()
        super()._handle_coordinator_update()

    def _update_value(self) -> None:
        if not self.coordinator.last_update_success:
            return
        wh = (self.coordinator.data or {}).get("routed_energy_total")
        kwh = None if wh is None else round(wh / 1000, 3)
        self._value, self._drop_since = monotonic_total(
            self._value, kwh, self._drop_since, dt_util.utcnow().timestamp()
        )

    @property
    def native_value(self) -> float | None:
        return self._value

    @property
    def extra_state_attributes(self) -> dict:
        return {"f1atb_kind": "routed_energy_total"}


@dataclass
class _RoutedTodayExtra(ExtraStoredData):
    """Persisted state of the daily total (survives an HA restart)."""

    accum_wh: float | None
    day: str | None

    def as_dict(self) -> dict:
        return {"accum_wh": self.accum_wh, "day": self.day}


class F1atbRoutedTodaySensor(F1atbBaseEntity, SensorEntity, RestoreEntity):
    """Routed energy today, computed by INTEGRATING the routed power.

    The firmware's own daily counter over-counts (especially when the router's power supply is
    cut: clock jumps at boot skew its integration). So the routed power (physically bounded and
    correct) is integrated on the HA side with trapezoids, reset at local midnight.
    """

    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_routed_energy_today"
        self._accum: float = 0.0          # Wh accumulated today
        self._day: str | None = None      # local date of the current total
        self._last_ts = None              # UTC datetime of the last integrated sample
        self._last_power: float = 0.0     # last routed power (W)
        self._value: float = 0.0          # kWh today

    @property
    def name(self) -> str:
        return self.coordinator.tr("routed_energy_today")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        extra = await self.async_get_last_extra_data()
        if extra is not None:
            d = extra.as_dict()
            self._accum = float(d.get("accum_wh") or 0.0)
            self._day = d.get("day")
        # If HA resumes on another day, the first sample resets to zero.
        self._value = round(self._accum / 1000.0, 3)

    @property
    def extra_restore_state_data(self) -> _RoutedTodayExtra:
        return _RoutedTodayExtra(self._accum, self._day)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._integrate()
        super()._handle_coordinator_update()

    def _integrate(self) -> None:
        # No integration while the router is unreachable (stale data).
        if not self.coordinator.last_update_success:
            return
        power = (self.coordinator.data or {}).get("routed_power")
        if power is None:
            return
        try:
            power = max(0.0, float(power))
        except (TypeError, ValueError):
            return

        now = dt_util.utcnow()
        today = dt_util.now().date().isoformat()

        if self._day != today:  # new day (or first time) → reset
            self._day = today
            self._accum = 0.0
            self._last_ts = now
            self._last_power = power
            self._value = 0.0
            return

        if self._last_ts is not None:
            dt = (now - self._last_ts).total_seconds()
            if 0 < dt <= INTEGRATION_MAX_DT:
                # Trapezoid: energy (Wh) = mean power × duration / 3600
                self._accum += (self._last_power + power) / 2.0 * dt / 3600.0
        self._last_ts = now
        self._last_power = power
        self._value = round(self._accum / 1000.0, 3)

    @property
    def native_value(self) -> float | None:
        return self._value

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "f1atb_kind": "routed_energy_today",
            "methode": self.coordinator.tr("energy_method"),
        }


class TemperatureSensor(F1atbBaseEntity, SensorEntity):
    """Temperature of a configured channel (internal DS18B20 / external / MQTT).

    A channel (0..3) is exposed when it is configured on the router (Source_Temp != "tempNo").
    The entity removes itself when the channel disappears from the config.
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator, channel: int) -> None:
        super().__init__(coordinator)
        self._channel = channel
        self._attr_unique_id = f"{coordinator.entry.unique_id}_temperature_{channel}"

    @property
    def _chan(self) -> dict | None:
        return (self.coordinator.data or {}).get("temp_channels", {}).get(self._channel)

    @property
    def name(self) -> str:
        c = self._chan
        return (c.get("name") if c else None) or self.coordinator.tr("temperature", channel=self._channel)

    @property
    def available(self) -> bool:
        c = self._chan
        return super().available and c is not None and c.get("value") is not None

    @property
    def native_value(self) -> float | None:
        c = self._chan
        if not c or c.get("value") is None:
            return None
        return round(float(c["value"]), 1)

    @property
    def extra_state_attributes(self) -> dict:
        c = self._chan or {}
        return {
            "f1atb_kind": "temperature",
            "temp_channel": self._channel,
            "source": c.get("source"),
            "nom": c.get("name"),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._remove_if_gone))

    @callback
    def _remove_if_gone(self) -> None:
        if not temp_channel_retained(self.coordinator.data, self._channel):
            self.hass.async_create_task(self.async_remove(force_remove=True))


class OpeningSensor(F1atbActionEntity, SensorEntity):
    """Current routing opening (%) of an active action."""

    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _kind = "ouverture"
    _name_key = "opening"

    def __init__(self, coordinator, index: int) -> None:
        super().__init__(coordinator, index)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_ouverture_{index}"

    @property
    def native_value(self) -> float | None:
        a = self._action
        return None if a is None else a.get("opening")


class _TankSensor(F1atbBaseEntity, SensorEntity):
    """Hot-water tank model output. Refreshed every minute, available while the router is off."""

    _key = ""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{self._key}"

    @property
    def name(self) -> str:
        return self.coordinator.tr(self._key)

    @property
    def available(self) -> bool:
        return self.coordinator.tank is not None and self.coordinator.tank.energy is not None

    @property
    def _doy(self) -> int:
        return dt_util.now().timetuple().tm_yday

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.coordinator.tank_signal, self.async_write_ha_state)
        )


class TankChargeSensor(_TankSensor):
    """Estimated charge of the hot-water tank (0 % = cold water, 100 % = set point)."""

    _key = "tank_charge"
    _attr_icon = "mdi:water-boiler"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        pct = self.coordinator.tank.percent(self._doy)
        return None if pct is None else round(pct, 1)

    @property
    def extra_state_attributes(self) -> dict:
        tank = self.coordinator.tank
        doy = self._doy
        last = tank.last_full
        return {
            "f1atb_kind": "tank_charge",
            "capacity_kwh": round(tank.capacity(doy), 2),
            "cold_water_c": round(cold_water_temp(doy), 1),
            "setpoint_c": tank.setpoint_c,
            "volume_l": tank.volume_l,
            "usage_l_day_40c": round(tank.usage_l_day_at(doy), 0),
            "losses_kwh_day": tank.loss_kwh_day,
            "last_full": last.isoformat() if last else None,
            "hours_since_full": (
                round((dt_util.now() - last).total_seconds() / 3600, 1) if last else None
            ),
        }


class TankEnergySensor(_TankSensor):
    """Heat stored in the tank above the cold-water temperature."""

    _key = "tank_energy"
    _attr_icon = "mdi:thermometer-water"
    _attr_device_class = SensorDeviceClass.ENERGY_STORAGE
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        energy = self.coordinator.tank.energy
        return None if energy is None else round(energy, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {"f1atb_kind": "tank_energy"}


class TankHotWaterSensor(_TankSensor):
    """Litres of water at 40 °C (mixed with cold water) the stored heat can still deliver."""

    _key = "tank_hot_water"
    _attr_icon = "mdi:shower-head"
    _attr_device_class = SensorDeviceClass.VOLUME_STORAGE
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        litres = self.coordinator.tank.litres_at(self._doy)
        return None if litres is None else round(litres)

    @property
    def extra_state_attributes(self) -> dict:
        return {"f1atb_kind": "tank_hot_water"}
