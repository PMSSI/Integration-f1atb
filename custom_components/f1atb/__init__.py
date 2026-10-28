"""F1ATB Solar Router integration (official firmware, local HTTP API)."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.loader import async_get_integration

from .api import F1atbApiError, F1atbClient
from .const import CONF_HOST, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import F1atbCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.BUTTON,
]
CARD_URL = f"/{DOMAIN}/f1atb-card.js"
SERVICE_SET_TANK_CHARGE = "set_tank_charge"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


async def _upsert_lovelace_resource(hass: HomeAssistant, url: str) -> None:
    """Declare the card as a dashboard resource too (storage mode), updated in place on each version.

    Dashboards load their resources themselves, which the mobile app does more reliably than the
    extra JS URLs (a phone kept showing "configuration error" with only the latter).
    """
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    if resources is None or not hasattr(resources, "async_create_item"):
        return  # YAML mode: resources are managed by the user
    if not getattr(resources, "loaded", True):
        await resources.async_load()
        resources.loaded = True
    base = url.split("?")[0]
    for item in resources.async_items():
        if item.get("url", "").split("?")[0] == base:
            if item["url"] != url:
                await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
            return
    await resources.async_create_item({"res_type": "module", "url": url})


async def _register_card(hass: HomeAssistant) -> None:
    """Serve the Lovelace card and load it automatically (available in the visual editor)."""
    if hass.data.get(f"{DOMAIN}_card"):
        return
    card = Path(__file__).parent / "f1atb-card.js"
    try:
        from homeassistant.components.http import StaticPathConfig

        # Cached like the HACS cards: the URL carries a hash of the file, so any change gives a new
        # URL and no browser (nor the mobile app, which keeps stale copies for days) runs an old card.
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(card), True)]
        )
        version = (await async_get_integration(hass, DOMAIN)).version
        url = f"{CARD_URL}?v={version}-{await hass.async_add_executor_job(_file_hash, card)}"
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, url)
        try:
            await _upsert_lovelace_resource(hass, url)
        except Exception as err:  # noqa: BLE001 - the extra JS URL above still loads the card
            _LOGGER.debug("Card not declared as a dashboard resource: %s", err)
        # Flagged only on success: a failure is retried at the next setup.
        hass.data[f"{DOMAIN}_card"] = True
    except Exception as err:  # noqa: BLE001 - non-blocking: the integration works without the card
        _LOGGER.warning("Cannot auto-load the card (%s). "
                        "Add %s as a Lovelace resource manually if needed.", err, CARD_URL)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _register_card(hass)
    session = async_get_clientsession(hass)
    client = F1atbClient(session, entry.data[CONF_HOST])

    scan = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = F1atbCoordinator(hass, entry, client, scan)

    # The router may be POWERED OFF (supply switched separately): that is NOT a configuration
    # error, so ConfigEntryNotReady is never raised (it would show "Setup failed"). The
    # integration loads, "Connected" turns off, the other entities are unavailable, and
    # everything fills in as soon as the router answers.
    try:
        coordinator.config = await client.async_get_config()
    except F1atbApiError as err:
        _LOGGER.warning("Router unreachable at startup (%s): loading in offline mode.", err)
        coordinator.config = {}

    # async_refresh() (NOT async_config_entry_first_refresh): never raises ConfigEntryNotReady.
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    if coordinator.tank is not None:
        await coordinator.async_tank_load()
        entry.async_on_unload(
            async_track_time_interval(hass, coordinator.async_tank_tick, timedelta(minutes=1))
        )
        _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_TANK_CHARGE):
        return

    async def _set_tank_charge(call: ServiceCall) -> None:
        """Manual correction of the estimated tank charge (e.g. "it is full right now")."""
        for coordinator in hass.data.get(DOMAIN, {}).values():
            coordinator.tank_set_percent(call.data["percent"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TANK_CHARGE,
        _set_tank_charge,
        schema=vol.Schema({vol.Required("percent"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100))}),
    )


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None:
            await coordinator.async_tank_save()
    return unload_ok
