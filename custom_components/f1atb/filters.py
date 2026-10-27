"""Pure helpers (no Home Assistant import), unit-tested in tests/test_filters.py."""
from __future__ import annotations

# A drop of the lifetime counter that lasts longer than this is accepted as a real
# counter reset (e.g. the energy meter was replaced) instead of a boot glitch.
COUNTER_DROP_ACCEPT_S = 3600


def monotonic_total(
    last: float | None, new: float | None, drop_since: float | None, now: float
) -> tuple[float | None, float | None]:
    """Filter a lifetime energy counter reported by the router.

    At boot the firmware reports its last *midnight* snapshot (possibly weeks old) or 0 until
    the first meter read. Feeding that to a TOTAL_INCREASING sensor makes the recorder see a
    meter reset, then count the whole lifetime total again on the next real reading.

    Returns (value to report, new drop_since): readings <= 0 are ignored, short drops keep the
    last good value, a drop lasting COUNTER_DROP_ACCEPT_S seconds becomes the new baseline.
    """
    if new is None or new <= 0:
        return last, drop_since
    if last is None or new >= last:
        return new, None
    if drop_since is None:
        return last, now
    if now - drop_since >= COUNTER_DROP_ACCEPT_S:
        return new, None
    return last, drop_since
