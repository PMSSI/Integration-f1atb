"""F1ATB button: automatic calibration of the max power (per active action)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import F1atbActionEntity
from .helpers import async_setup_action_platform


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    def factory(index: int) -> list:
        return [CalibrationButton(coordinator, index)]

    async_setup_action_platform(entry, coordinator, async_add_entities, factory)


class CalibrationButton(F1atbActionEntity, ButtonEntity):
    """Start the calibration: open to 100 %, measure the routed power, store it.

    Manual entry of the max power is still possible (both write the same value; the last
    one wins).
    """

    _attr_icon = "mdi:ruler"
    _attr_entity_category = EntityCategory.CONFIG
    _kind = "calibrer"
    _name_key = "calibrate"

    def __init__(self, coordinator, index: int) -> None:
        super().__init__(coordinator, index)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_calibrer_{index}"

    async def async_press(self) -> None:
        # Background task: the procedure takes ~20 s (settling time + 10 s average).
        self.coordinator.entry.async_create_background_task(
            self.hass, self.coordinator.async_calibrate(self._index), "f1atb_calibration"
        )
