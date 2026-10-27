"""Common base for F1ATB entities."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import F1atbCoordinator
from .helpers import action_retained


class F1atbBaseEntity(CoordinatorEntity[F1atbCoordinator]):
    """Entity attached to the router device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: F1atbCoordinator) -> None:
        super().__init__(coordinator)
        cfg = coordinator.config or {}
        uid = coordinator.entry.unique_id or coordinator.entry.entry_id
        # Router powered off: the config is empty → fall back to the entry title (the router
        # name, set by the config flow) so the device is not renamed.
        name = (
            cfg.get("Routeur")
            or cfg.get("hostname")
            or coordinator.entry.title
            or "F1ATB router"
        )
        info = DeviceInfo(
            identifiers={(DOMAIN, str(uid))},
            name=name,
            manufacturer="F1ATB",
            model="Solar Router (RMS ESP32)",
            configuration_url=coordinator.client.base_url,
        )
        version = cfg.get("VersionStocke")
        if version:  # do not erase the known version while the router is off
            info["sw_version"] = str(version)
        self._attr_device_info = info


class F1atbActionEntity(F1atbBaseEntity):
    """Entity bound to ONE action (index). Removes itself when the action is disabled."""

    _kind: str = ""  # role used by the Lovelace card (forme_onde, ouverture_max…)
    _name_key: str = ""  # i18n key of the entity name

    def __init__(self, coordinator: F1atbCoordinator, index: int) -> None:
        super().__init__(coordinator)
        self._index = index
        self._last_name: str | None = None

    @property
    def _action(self) -> dict | None:
        return (self.coordinator.data or {}).get("actions", {}).get(self._index)

    @property
    def name(self) -> str:
        return self.coordinator.tr(self._name_key, action=self._action_name)

    @property
    def extra_state_attributes(self) -> dict:
        # Lets the card group entities reliably (per action + role).
        return {
            "f1atb_kind": self._kind,
            "action_index": self._index,
            "action_name": self._action_name,
        }

    @property
    def _action_name(self) -> str:
        a = self._action
        if a and a.get("name"):
            self._last_name = a["name"]
        # keep the last known name while the action is briefly missing
        return self._last_name or self.coordinator.tr("action", index=self._index)

    @property
    def _config_ok(self) -> bool:
        """Is the config (/ParaFixe) of this action known? (otherwise mode/ForceOuvre = 0)."""
        a = self._action
        return bool(a and a.get("config_ok"))

    @property
    def available(self) -> bool:
        return super().available and self._action is not None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._remove_if_disabled))

    @callback
    def _remove_if_disabled(self) -> None:
        if not action_retained(self.coordinator.data, self._index):
            self.hass.async_create_task(self.async_remove(force_remove=True))

    async def _write_and_refresh(self, config_change: bool) -> None:
        """After a write: re-read (config if needed) and update the HA state."""
        if config_change:
            await self.coordinator.async_refresh_config()
        await self.coordinator.async_request_refresh()
