"""Entity names and select options in the language chosen during setup.

The French strings are the historical ones: they must not change, since entity names and
select options can be referenced by existing dashboards and automations.
"""
from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "fr": {
        "grid_import_power": "Soutirée réseau",
        "grid_export_power": "Injectée réseau",
        "routed_power": "Puissance routée",
        "routed_energy_total": "Énergie routée totale",
        "routed_energy_today": "Énergie routée aujourd'hui",
        "connected": "Connecté",
        "temperature": "Température {channel}",
        "action": "Action {index}",
        "opening": "{action} ouverture",
        "waveform": "{action} forme d'onde",
        "forcing": "{action} forçage",
        "forced_opening": "{action} ouverture (marche forcée)",
        "auto_max_opening": "{action} ouverture max (Auto)",
        "max_power": "{action} puissance max",
        "forced_power": "{action} marche forcée (W)",
        "calibrate": "{action} calibrer puissance max",
        "mode_0": "Inactif",
        "mode_1_triac": "Découpe sinus",
        "mode_1_relay": "On/Off",
        "mode_2": "Multi-sinus",
        "mode_3": "Train de sinus",
        "mode_4": "PWM",
        "mode_5": "Demi-sinus",
        "force_auto": "Auto",
        "force_on": "Forcé Marche",
        "force_off": "Forcé Arrêt",
        "energy_method": "intégration de la puissance (HA)",
        "calib_title": "F1ATB — calibration sans effet",
        "calib_message": (
            "La calibration de **{action}** n'a mesuré **aucune puissance routée**.\n\n"
            "L'appareil consomme-t-il réellement pendant la mesure ? "
            "(ex. chauffe-eau déjà chaud, thermostat coupé, disjoncteur ouvert).\n\n"
            "➡️ La puissance max **n'a pas été modifiée**. Relancez la calibration quand "
            "l'appareil peut consommer, ou saisissez la valeur manuellement."
        ),
    },
    "en": {
        "grid_import_power": "Grid import",
        "grid_export_power": "Grid export",
        "routed_power": "Routed power",
        "routed_energy_total": "Routed energy total",
        "routed_energy_today": "Routed energy today",
        "connected": "Connected",
        "temperature": "Temperature {channel}",
        "action": "Action {index}",
        "opening": "{action} opening",
        "waveform": "{action} waveform",
        "forcing": "{action} override",
        "forced_opening": "{action} forced-on opening",
        "auto_max_opening": "{action} max opening (auto)",
        "max_power": "{action} max power",
        "forced_power": "{action} forced-on power (W)",
        "calibrate": "{action} calibrate max power",
        "mode_0": "Inactive",
        "mode_1_triac": "Phase cut",
        "mode_1_relay": "On/Off",
        "mode_2": "Multi-sine",
        "mode_3": "Sine train",
        "mode_4": "PWM",
        "mode_5": "Half-sine",
        "force_auto": "Auto",
        "force_on": "Forced on",
        "force_off": "Forced off",
        "energy_method": "power integration (HA)",
        "calib_title": "F1ATB — calibration had no effect",
        "calib_message": (
            "Calibrating **{action}** measured **no routed power**.\n\n"
            "Is the appliance actually drawing power during the measurement? "
            "(e.g. water heater already hot, thermostat open, breaker off).\n\n"
            "➡️ The max power **was not changed**. Run the calibration again when the appliance "
            "can draw power, or enter the value manually."
        ),
    },
}


def resolve_language(option: str | None, ha_language: str | None) -> str:
    """Setup option ("auto", "fr", "en") → "fr" or "en"."""
    if option in STRINGS:
        return option
    return "fr" if (ha_language or "").lower().startswith("fr") else "en"


def tr(language: str, key: str, **kwargs) -> str:
    text = STRINGS.get(language, STRINGS["en"]).get(key) or STRINGS["en"][key]
    return text.format(**kwargs) if kwargs else text
