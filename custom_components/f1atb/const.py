"""Constants for the F1ATB Solar Router integration."""
from __future__ import annotations

DOMAIN = "f1atb"

CONF_HOST = "host"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_FORCE_MINUTES = "force_minutes"
CONF_LANGUAGE = "language"

DEFAULT_SCAN_INTERVAL = 5  # seconds
DEFAULT_FORCE_MINUTES = 720  # duration of a forced on/off, in minutes (12 h)

# Hot-water tank model (0 L = disabled)
CONF_TANK_VOLUME = "tank_volume"
CONF_TANK_SETPOINT = "tank_setpoint"
DEFAULT_TANK_VOLUME = 0
DEFAULT_TANK_SETPOINT = 60

LANGUAGE_AUTO = "auto"  # follow the Home Assistant language
LANGUAGES = [LANGUAGE_AUTO, "fr", "en"]

# Consecutive failed polls tolerated before the router is reported offline
# (a busy ESP32 or a Wi-Fi blip must not make every entity unavailable).
FAILURES_BEFORE_OFFLINE = 3
