"""F1ATB selects: waveform (mode) and override (forced on / off)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_FORCE_MINUTES, DEFAULT_FORCE_MINUTES, DOMAIN
from .entity import F1atbActionEntity
from .helpers import (
    async_setup_action_platform,
    mode_label_to_value,
    mode_options,
    mode_value_to_label,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    def factory(index: int) -> list:
        return [
            WaveformSelect(coordinator, index),
            OverrideSelect(coordinator, index, entry),
        ]

    async_setup_action_platform(entry, coordinator, async_add_entities, factory)


class WaveformSelect(F1atbActionEntity, SelectEntity):
    """Waveform (mode) of the action. Written with /ParaNew (persistent)."""

    _attr_icon = "mdi:sine-wave"
    _kind = "forme_onde"
    _name_key = "waveform"

    def __init__(self, coordinator, index: int) -> None:
        super().__init__(coordinator, index)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_forme_onde_{index}"

    @property
    def available(self) -> bool:
        # The mode comes from /ParaFixe: no config = no misleading "Inactive".
        return super().available and self._config_ok

    @property
    def _is_triac(self) -> bool:
        a = self._action
        return bool(a.get("is_triac")) if a else self._index == 0

    @property
    def options(self) -> list[str]:
        return mode_options(self.coordinator.language, self._is_triac)

    @property
    def current_option(self) -> str | None:
        a = self._action
        if not a:
            return None
        return mode_value_to_label(self.coordinator.language, a.get("mode", 0), self._is_triac)

    async def async_select_option(self, option: str) -> None:
        value = mode_label_to_value(self.coordinator.language, option, self._is_triac)
        if value is None:
            return
        idx = self._index

        def _mutate(config: dict) -> None:
            actions = config.get("Actions") or []
            if 0 <= idx < len(actions):
                actions[idx]["Actif"] = value

        await self.coordinator.client.async_patch_config(_mutate)
        await self._write_and_refresh(config_change=True)


class OverrideSelect(F1atbActionEntity, SelectEntity):
    """Routing override: auto / forced on / forced off. Written with /ForceAction."""

    _attr_icon = "mdi:gesture-tap-button"
    _kind = "forcage"
    _name_key = "forcing"

    def __init__(self, coordinator, index: int, entry: ConfigEntry) -> None:
        super().__init__(coordinator, index)
        self._entry = entry
        self._attr_unique_id = f"{coordinator.entry.unique_id}_forcage_{index}"

    @property
    def options(self) -> list[str]:
        # Order matters: the card relies on [auto, forced on, forced off].
        tr = self.coordinator.tr
        return [tr("force_auto"), tr("force_on"), tr("force_off")]

    @property
    def current_option(self) -> str | None:
        a = self._action
        if not a:
            return None
        force = a.get("force", 0) or 0
        auto, forced_on, forced_off = self.options
        if force > 0:
            return forced_on
        if force < 0:
            return forced_off
        return auto

    @property
    def extra_state_attributes(self) -> dict:
        a = self._action
        force = (a.get("force", 0) or 0) if a else 0
        return {**super().extra_state_attributes, "minutes_restantes": abs(force)}

    async def async_select_option(self, option: str) -> None:
        minutes = int(self._entry.options.get(CONF_FORCE_MINUTES, DEFAULT_FORCE_MINUTES))
        _, forced_on, forced_off = self.options
        if option == forced_on:
            force = minutes
        elif option == forced_off:
            force = -minutes
        else:
            force = 0
        await self.coordinator.client.async_force_action(self._index, force)
        await self._write_and_refresh(config_change=False)
