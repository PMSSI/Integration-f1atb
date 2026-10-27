"""Estimated state of charge of a hot-water tank heated through the router (pure Python).

There is no temperature probe: the stored energy E (kWh above the cold-water temperature) is
integrated minute by minute and re-anchored every time the tank is seen full.

    dE/dt = heater power − standing losses − hot-water draws

- Heater power: measured by the router (routed power).
- Standing losses: `loss_kwh_day` when full, proportional to the stored energy.
- Draws: `usage_l_day` litres per day at the set point, spread over a typical domestic
  profile (mornings and evenings). The energy of one litre depends on the cold-water
  temperature, which follows the season (about 9 °C in February, 19 °C in August).
- Anchor: the router wants to route (opening >= 10 %, i.e. there is surplus or a forced-on)
  but the heater draws no power for 3 minutes → its thermostat has cut → the tank is full.
  At each anchor the daily usage is corrected from the drift of the model since the previous
  anchor, so the model learns the household consumption by itself.
"""
from __future__ import annotations

from datetime import datetime
import math

WH_PER_L_K = 1.163  # energy to heat one litre of water by 1 °C (Wh)
KWH_PER_L_K = WH_PER_L_K / 1000

FULL_OPENING_MIN = 10  # % — the router wants to route
FULL_POWER_MAX = 30  # W — …but the heater draws (almost) nothing
FULL_SECONDS = 180  # sustained for 3 minutes
LEARN_MIN_DAYS = 0.5  # shorter intervals carry too little information
LEARN_RATE = 0.5
MAX_STEP_S = 86400  # never integrate more than a day at once (HA downtime)

# Share of the daily hot-water draws per hour of the day (typical household).
_PROFILE = [0.5, 0.3, 0.2, 0.2, 0.3, 1.0, 4.0, 7.0, 6.0, 3.5, 2.0, 1.5,
            1.5, 1.2, 1.0, 1.0, 1.2, 2.0, 4.0, 5.5, 5.0, 3.5, 2.0, 1.0]
PROFILE = [w / sum(_PROFILE) for w in _PROFILE]


def cold_water_temp(day_of_year: int) -> float:
    """Mains water temperature (France): mean 14 °C, ±5 °C, warmest mid-August."""
    return 14.0 + 5.0 * math.cos(2 * math.pi * (day_of_year - 227) / 365.25)


def default_loss_kwh_day(volume_l: float) -> float:
    """Standing losses of a full tank (ErP class B/C): about 0.6 kWh per 100 L per day."""
    return round(0.006 * volume_l, 2)


class TankModel:
    def __init__(
        self,
        volume_l: float,
        setpoint_c: float = 60.0,
        loss_kwh_day: float | None = None,
        usage_l_day: float | None = None,
    ) -> None:
        self.volume_l = float(volume_l)
        self.setpoint_c = float(setpoint_c)
        self.loss_kwh_day = (
            default_loss_kwh_day(volume_l) if loss_kwh_day is None else float(loss_kwh_day)
        )
        # litres per day at the set point; default ≈ 15 % of the volume
        self.usage_l_day = 0.15 * self.volume_l if usage_l_day is None else float(usage_l_day)
        self.energy: float | None = None  # kWh above cold water, clamped to [0, capacity]
        self.free: float | None = None  # same integration without clamping (learning)
        self.last_full: datetime | None = None
        self.last_update: datetime | None = None
        self._full_seconds = 0.0
        self.full_now = False  # thermostat cut detected (sustained)

    # ------------------------------------------------------------------ physics
    def delta_t(self, day_of_year: int) -> float:
        return max(1.0, self.setpoint_c - cold_water_temp(day_of_year))

    def capacity(self, day_of_year: int) -> float:
        return self.volume_l * KWH_PER_L_K * self.delta_t(day_of_year)

    def percent(self, day_of_year: int) -> float | None:
        if self.energy is None:
            return None
        return 100.0 * self.energy / self.capacity(day_of_year)

    def litres_at(self, day_of_year: int, temp_c: float = 40.0) -> float | None:
        """Volume of water at temp_c (mixed with cold water) the stored energy can deliver."""
        if self.energy is None:
            return None
        rise = temp_c - cold_water_temp(day_of_year)
        return self.energy / (KWH_PER_L_K * rise) if rise > 0 else None

    def usage_l_day_at(self, day_of_year: int, temp_c: float = 40.0) -> float:
        rise = temp_c - cold_water_temp(day_of_year)
        return self.usage_l_day * self.delta_t(day_of_year) / rise if rise > 0 else 0.0

    # ------------------------------------------------------------------ dynamics
    def step(
        self,
        now: datetime,
        power_w: float,
        wants_to_route: bool,
        energy_wh: float | None = None,
    ) -> bool:
        """Advance the model to `now` (local time). Returns True when a full tank was detected.

        `power_w`: current heater power (0 if the router is offline), used for the full-tank
        detection and, without `energy_wh`, for the integration.
        `wants_to_route`: the router's opening is >= FULL_OPENING_MIN.
        `energy_wh`: energy actually delivered since the previous step (meter delta), more
        accurate than sampling the power once per step.
        """
        doy = now.timetuple().tm_yday
        cap = self.capacity(doy)
        if self.energy is None:
            self.energy = self.free = 0.7 * cap  # unknown until the first full tank
        if self.last_update is None:
            self.last_update = now
            return False
        dt = (now - self.last_update).total_seconds()
        self.last_update = now
        if dt <= 0:
            return False
        dt = min(dt, MAX_STEP_S)
        hours = dt / 3600
        losses = self.loss_kwh_day / 24 * (self.energy / cap) * hours
        draws = self.usage_l_day * KWH_PER_L_K * self.delta_t(doy) * PROFILE[now.hour] * hours
        heat = energy_wh / 1000 if energy_wh is not None else max(0.0, power_w) / 1000 * hours
        d_e = heat - losses - draws
        self.energy = min(cap, max(0.0, self.energy + d_e))
        self.free += d_e

        if wants_to_route and power_w < FULL_POWER_MAX:
            self._full_seconds += dt
        else:
            self._full_seconds = 0.0
            self.full_now = False
        if self._full_seconds >= FULL_SECONDS and not self.full_now:
            self.full_now = True
            self._anchor(now, cap, doy)
            return True
        return False

    def _anchor(self, now: datetime, cap: float, doy: int) -> None:
        if self.last_full is not None and self.free is not None:
            days = (now - self.last_full).total_seconds() / 86400
            if days >= LEARN_MIN_DAYS:
                # free > cap: the model consumed too little → more usage than assumed
                error_kwh_day = (self.free - cap) / days
                self.usage_l_day += LEARN_RATE * error_kwh_day / (KWH_PER_L_K * self.delta_t(doy))
                self.usage_l_day = min(max(self.usage_l_day, 0.0), 2 * self.volume_l)
        self.energy = self.free = cap
        self.last_full = now

    def set_percent(self, now: datetime, percent: float) -> None:
        """Manual correction (e.g. "the tank is full right now")."""
        cap = self.capacity(now.timetuple().tm_yday)
        self.energy = self.free = cap * min(max(percent, 0.0), 100.0) / 100
        self.last_update = now

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> dict:
        return {
            "energy": self.energy,
            "free": self.free,
            "usage_l_day": self.usage_l_day,
            "last_full": self.last_full.isoformat() if self.last_full else None,
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }

    def restore(self, data: dict) -> None:
        self.energy = data.get("energy")
        self.free = data.get("free", self.energy)
        if data.get("usage_l_day") is not None:
            self.usage_l_day = float(data["usage_l_day"])
        for key in ("last_full", "last_update"):
            value = data.get(key)
            setattr(self, key, datetime.fromisoformat(value) if value else None)
