"""F1ATB binary sensor: router connectivity (always present)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import F1atbBaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list = [F1atbConnectedBinarySensor(coordinator)]
    if coordinator.tank is not None:
        entities.append(TankFullBinarySensor(coordinator))
    async_add_entities(entities)


class F1atbConnectedBinarySensor(F1atbBaseEntity, BinarySensorEntity):
    """Connected: ON while the router answers, OFF otherwise.

    ALWAYS available (unlike the other entities) so it can report the disconnected state →
    tracks when the router is running (history), and can drive a card's visibility.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:router-wireless"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_connected"

    @property
    def name(self) -> str:
        return self.coordinator.tr("connected")

    @property
    def available(self) -> bool:
        # Always available: must be able to show "disconnected" when the router is off.
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success)

    @property
    def extra_state_attributes(self) -> dict:
        # f1atb_language: the card displays its labels in the language chosen at setup.
        return {"f1atb_kind": "connected", "f1atb_language": self.coordinator.language}


class TankFullBinarySensor(F1atbBaseEntity, BinarySensorEntity):
    """Tank full detected: the router wants to route (surplus or forced on) but the heater has
    drawn no power for 3 minutes → its thermostat has cut. Off as soon as power flows again or
    the router stops routing. Good trigger for a "stop heating, the tank is full" automation.
    """

    _attr_icon = "mdi:water-boiler-off"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_tank_full"

    @property
    def name(self) -> str:
        return self.coordinator.tr("tank_full")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.tank and self.coordinator.tank.full_now)

    @property
    def extra_state_attributes(self) -> dict:
        return {"f1atb_kind": "tank_full"}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.coordinator.tank_signal, self.async_write_ha_state)
        )
