"""Tests for filters.py and i18n.py (no Home Assistant needed): python tests/test_filters.py"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "f1atb"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


filters = _load("filters")
i18n = _load("i18n")
H = filters.COUNTER_DROP_ACCEPT_S


def test_counter_normal_growth():
    assert filters.monotonic_total(None, 1000.0, None, 0) == (1000.0, None)
    assert filters.monotonic_total(1000.0, 1000.5, None, 5) == (1000.5, None)


def test_counter_boot_glitches_are_ignored():
    # 0 and None readings never reach the sensor
    assert filters.monotonic_total(1312.7, 0.0, None, 10) == (1312.7, None)
    assert filters.monotonic_total(1312.7, None, None, 10) == (1312.7, None)
    # stale midnight snapshot right after boot: keep the last good value...
    value, since = filters.monotonic_total(1312.7, 1290.1, None, 100)
    assert value == 1312.7 and since == 100
    # ...then the first real meter read continues normally
    assert filters.monotonic_total(1312.7, 1312.9, since, 105) == (1312.9, None)


def test_counter_real_reset_is_accepted_after_an_hour():
    value, since = filters.monotonic_total(1312.7, 3.2, None, 0)
    assert value == 1312.7
    value, since = filters.monotonic_total(value, 3.4, since, H - 1)
    assert value == 1312.7
    assert filters.monotonic_total(value, 3.6, since, H) == (3.6, None)


def test_language_resolution_and_french_names_unchanged():
    assert i18n.resolve_language("auto", "fr") == "fr"
    assert i18n.resolve_language("auto", "fr-CA") == "fr"
    assert i18n.resolve_language("auto", "de") == "en"
    assert i18n.resolve_language("en", "fr") == "en"
    assert i18n.resolve_language(None, None) == "en"
    # historical French names/options (dashboards and automations rely on them)
    assert i18n.tr("fr", "waveform", action="R1") == "R1 forme d'onde"
    assert i18n.tr("fr", "forced_power", action="R1") == "R1 marche forcée (W)"
    assert i18n.tr("fr", "force_on") == "Forcé Marche"
    assert i18n.tr("fr", "mode_5") == "Demi-sinus"
    assert i18n.tr("en", "waveform", action="R1") == "R1 waveform"
    assert set(i18n.STRINGS["fr"]) == set(i18n.STRINGS["en"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
