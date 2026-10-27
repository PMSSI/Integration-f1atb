"""F1ATB Solar Router integration (official firmware, local HTTP API)."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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


async def _register_card(hass: HomeAssistant) -> None:
    """Serve the Lovelace card and load it automatically (available in the visual editor)."""
    if hass.data.get(f"{DOMAIN}_card"):
        return
    card = Path(__file__).parent / "f1atb-card.js"
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(card), False)]
        )
        from homeassistant.components.frontend import add_extra_js_url

        # ?v= makes browsers and the mobile app reload the card after an update
        # (otherwise phones can keep running an old card for days).
        version = (await async_get_integration(hass, DOMAIN)).version
        add_extra_js_url(hass, f"{CARD_URL}?v={version}")
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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
