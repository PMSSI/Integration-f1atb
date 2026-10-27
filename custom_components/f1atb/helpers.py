"""Shared helpers: waveform modes, active actions and dynamic entity setup."""
from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import F1atbCoordinator
from .i18n import tr

# --- Modes ("Actif" field of the F1ATB config) ---
# Order of the list = display order.
# Actif=1: "phase cut" for the triac (action 0) / "On/Off" for a relay.
MODE_ORDER = [0, 1, 5, 2, 3, 4]


def _labels(language: str, is_triac: bool) -> dict[int, str]:
    labels = {v: tr(language, f"mode_{v}") for v in (0, 2, 3, 4, 5)}
    labels[1] = tr(language, "mode_1_triac" if is_triac else "mode_1_relay")
    return labels


def mode_options(language: str, is_triac: bool) -> list[str]:
    labels = _labels(language, is_triac)
    return [labels[v] for v in MODE_ORDER]


def mode_value_to_label(language: str, value: int | None, is_triac: bool) -> str | None:
    return _labels(language, is_triac).get(int(value or 0))


def mode_label_to_value(language: str, label: str, is_triac: bool) -> int | None:
    for v, text in _labels(language, is_triac).items():
        if text == label:
            return v
    return None


def active_action_indices(data: dict | None) -> set[int]:
    """Indices of the ACTIVE actions (/ajax_etatActions only lists active ones)."""
    if not data:
        return set()
    return set((data.get("actions") or {}).keys())


def action_retained(data: dict | None, index: int) -> bool:
    """Should the entities of this action be kept?

    Removed only when the router config says the action is disabled (Actif == 0). An action
    that just vanished from /ajax_etatActions (missed poll, triac without zero-cross signal)
    keeps its entities, shown as unavailable, so history and automations are not broken.
    """
    if not data:
        return True
    if index in (data.get("actions") or {}):
        return True
    configured = data.get("configured_actions")
    return configured is None or index in configured


def temp_channel_indices(data: dict | None) -> set[int]:
    """Configured temperature channels (0..3)."""
    if not data:
        return set()
    return set((data.get("temp_channels") or {}).keys())


def temp_channel_retained(data: dict | None, channel: int) -> bool:
    return not data or channel in (data.get("temp_channels") or {})


@callback
def async_setup_action_platform(
    entry: ConfigEntry,
    coordinator: F1atbCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[int], Iterable],
    keys_fn: Callable[[dict | None], set[int]] = active_action_indices,
    retained_fn: Callable[[dict | None, int], bool] = action_retained,
) -> None:
    """Create entities per key (active action or temperature channel), re-add them on return.

    `factory(index)` returns the entities to create, `keys_fn(data)` the current keys.
    REMOVAL is done by each entity (self-removal) with the same `retained_fn` rule, so a key is
    only forgotten here once its entities are gone (no duplicates when it comes back).
    """
    known: set[int] = set()

    @callback
    def _sync() -> None:
        data = coordinator.data
        new: list = []
        for idx in keys_fn(data):
            if idx not in known:
                known.add(idx)
                new.extend(factory(idx))
        for idx in [k for k in known if not retained_fn(data, k)]:
            known.discard(idx)
        if new:
            async_add_entities(new)

    _sync()
    entry.async_on_unload(coordinator.async_add_listener(_sync))
