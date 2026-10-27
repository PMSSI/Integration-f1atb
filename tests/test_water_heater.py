"""Tests for water_heater.py (no Home Assistant needed): python tests/test_water_heater.py"""
from datetime import datetime, timedelta
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "water_heater", Path(__file__).resolve().parent.parent / "custom_components" / "f1atb" / "water_heater.py"
)
wh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wh)
T0 = datetime(2026, 10, 20, 9, 0)


def run(model, start, minutes, power_w=0.0, wants=False):
    detected = False
    for m in range(1, minutes + 1):
        detected |= model.step(start + timedelta(minutes=m), power_w, wants)
    return start + timedelta(minutes=minutes), detected


def test_cold_water_and_capacity_follow_the_season():
    assert 8.5 < wh.cold_water_temp(46) < 9.5 and 18.5 < wh.cold_water_temp(227) < 19.5
    m = wh.TankModel(300, 60)
    assert m.capacity(46) > m.capacity(227) > 14
    assert abs(m.capacity(227) - 300 * 1.163e-3 * (60 - wh.cold_water_temp(227))) < 1e-9


def test_full_tank_needs_three_minutes_of_cut_thermostat():
    m = wh.TankModel(300, 60)
    m.step(T0, 0, False)
    t, detected = run(m, T0, 2, power_w=5, wants=True)
    assert not detected
    t, detected = run(m, t, 1, power_w=5, wants=True)
    assert detected and m.full_now and abs(m.percent(293) - 100) < 1e-6
    # no surplus (router closed): no power is NOT a full tank
    m2 = wh.TankModel(300, 60); m2.step(T0, 0, False)
    _, detected = run(m2, T0, 30, power_w=0, wants=False)
    assert not detected


def test_heating_raises_charge_and_draws_lower_it():
    m = wh.TankModel(300, 60); m.step(T0, 0, False)
    start = m.energy
    t, _ = run(m, T0, 60, power_w=3000)
    assert 2.6 < m.energy - start < 3.0  # 3 kWh in, minus a little loss and draw
    before = m.energy
    evening = t.replace(hour=19)
    m.last_update = evening
    run(m, evening, 120)  # evening draws, no heating
    assert before - m.energy > 0.3


def test_learning_corrects_usage_in_the_right_direction():
    for real_extra, sign in ((+2.0, +1), (-2.0, -1)):
        m = wh.TankModel(300, 60, usage_l_day=40); m.step(T0, 0, False)
        t, _ = run(m, T0, 3, power_w=0, wants=True)  # first anchor
        assert m.last_full is not None
        # one day later: the model drifted by real_extra kWh, then the tank is full again
        m.free += real_extra
        m.last_full -= timedelta(days=1)
        before = m.usage_l_day
        m.full_now = False
        run(m, t, 3, power_w=0, wants=True)
        assert (m.usage_l_day - before) * sign > 0, (real_extra, before, m.usage_l_day)


def test_restore_round_trip_and_downtime_cap():
    m = wh.TankModel(300, 60); m.step(T0, 0, False); run(m, T0, 10, power_w=1000)
    m2 = wh.TankModel(300, 60); m2.restore(m.to_dict())
    assert m2.energy == m.energy and m2.last_update == m.last_update and m2.usage_l_day == m.usage_l_day
    e = m2.energy
    m2.step(m2.last_update + timedelta(days=5), 0, False)  # 5 days of HA downtime
    assert m2.energy >= 0 and e - m2.energy < m2.capacity(298)  # at most one day integrated


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
