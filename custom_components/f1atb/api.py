"""Async HTTP client for the F1ATB solar router (official firmware).

Needs NO firmware change: it uses the router's existing web API
(/ajax_data, /ajax_etatActions, /ajax_dataESP32, /ParaFixe, /ParaNew, /ForceAction).
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
import logging

from aiohttp import ClientError, ClientSession

from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

# Separators used by the F1ATB firmware
GS = chr(29)  # Group Separator
RS = chr(30)  # Record Separator
US = chr(31)  # Unit Separator

TIMEOUT = 10


class F1atbApiError(HomeAssistantError):
    """Communication error with the router.

    A HomeAssistantError, so a failed write coming from a service call is shown to the user
    as a clean error message instead of an unhandled exception with a traceback.
    """


def _f(lst: list[str], i: int) -> float | None:
    try:
        return float(lst[i])
    except (IndexError, ValueError, TypeError):
        return None


def _i(val: str) -> int | None:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


class F1atbClient:
    """Talks to an F1ATB router through its local HTTP API."""

    def __init__(self, session: ClientSession, host: str) -> None:
        host = host.strip().rstrip("/")
        if not host.startswith("http://") and not host.startswith("https://"):
            host = "http://" + host
        self._base = host
        self._session = session
        # /ParaNew replaces the WHOLE configuration: read-modify-write cycles must not overlap,
        # otherwise the second write silently restores what the first one changed.
        self._write_lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return self._base

    async def _get(self, path: str) -> str:
        url = self._base + path
        try:
            async with asyncio.timeout(TIMEOUT):
                async with self._session.get(url) as resp:
                    resp.raise_for_status()
                    return await resp.text(errors="replace")
        except (ClientError, TimeoutError) as err:
            raise F1atbApiError(f"Request failed {url}: {err}") from err

    async def _post_plain(self, path: str, body: str) -> str:
        url = self._base + path
        # IMPORTANT: Content-Type text/plain → the firmware reads the raw body with
        # server.arg("plain"). With application/x-www-form-urlencoded it would parse it as a
        # form and ignore the JSON (the POST is accepted but has NO effect).
        headers = {"Content-Type": "text/plain"}
        try:
            async with asyncio.timeout(TIMEOUT):
                async with self._session.post(
                    url, data=body.encode("utf-8"), headers=headers
                ) as resp:
                    resp.raise_for_status()
                    return await resp.text(errors="replace")
        except (ClientError, TimeoutError) as err:
            raise F1atbApiError(f"POST failed {url}: {err}") from err

    # ---------------------------------------------------------------- read
    async def async_get_config(self) -> dict:
        """/ParaFixe: configuration (JSON). Identifies the device and its actions."""
        txt = await self._get("/ParaFixe")
        try:
            return json.loads(txt)
        except ValueError as err:
            raise F1atbApiError(f"/ParaFixe: invalid JSON: {err}") from err

    async def async_get_data(self) -> dict:
        """/ajax_data + /ajax_etatActions + /ajax_dataESP32 merged into one dict.

        /ajax_etatActions is mandatory: if it failed silently, every action would look
        inactive and all action entities would be removed, then re-created at the next poll.
        """
        data: dict = {"actions": {}}

        # ---- /ajax_data: house powers & energies + routed probe ----
        txt = await self._get("/ajax_data")
        groups = txt.split(GS)
        g0 = groups[0].split(RS) if groups else []
        house = groups[1].split(RS) if len(groups) > 1 else []
        probe = groups[2].split(RS) if len(groups) > 2 else []

        data["date"] = g0[1].strip() if len(g0) > 1 else None
        data["source"] = g0[2].strip() if len(g0) > 2 else None
        data["grid_import_power"] = _f(house, 0)          # PwS_M (drawn from the grid)
        data["grid_export_power"] = _f(house, 1)          # PwI_M (fed into the grid)
        data["house_energy_import_today"] = _f(house, 4)  # EAJS_M (Wh)
        data["house_energy_export_today"] = _f(house, 5)  # EAJI_M (Wh)
        data["routed_power"] = _f(probe, 0)               # PwS_T (routed to the load)
        data["routed_energy_today"] = _f(probe, 4)        # EAJS_T (Wh, firmware daily counter, unreliable)
        data["routed_energy_total"] = _f(probe, 6)        # Energie_T_Soutiree (Wh, lifetime)

        # temperatures (pipe-separated in g0[5])
        temps = []
        if len(g0) > 5:
            for t in g0[5].split("|"):
                try:
                    v = float(t)
                except ValueError:
                    v = None
                temps.append(v if v is not None and v > -100 else None)  # -127 = no probe
        data["temperatures"] = temps

        # ---- /ajax_etatActions: state of every ACTIVE action ----
        txt2 = await self._get("/ajax_etatActions")
        g = txt2.split(GS)
        # g = [temps, source, RMSextIP, NbActifs, rec1, rec2, ...]
        for rec in g[4:]:
            f = rec.split(RS)
            if len(f) < 4 or not f[0].strip():
                continue
            idx = _i(f[0])
            if idx is None:
                continue
            opening_raw = f[2].strip()
            if opening_raw in ("On", "on"):
                opening = 100
            elif opening_raw in ("Off", "off"):
                opening = 0
            else:
                opening = _i(opening_raw)
            data["actions"][idx] = {
                "index": idx,
                "name": f[1].strip(),
                "opening": opening,      # 0-100 %
                "force": _i(f[3]) or 0,  # tOnOff: >0 forced on (min), <0 forced off
            }

        # ---- /ajax_dataESP32: system info (optional) ----
        try:
            txt3 = await self._get("/ajax_dataESP32")
            m = txt3.split(GS)[0].split(RS)
            data["uptime_hours"] = _f(m, 0)
            data["rssi"] = _f(m, 2)
            data["heap_free"] = _f(m, 13)
            data["heap_min"] = _f(m, 14)
            ips = m[7].split(US) if len(m) > 7 else []
            data["ip"] = ips[0] if ips else None
        except (F1atbApiError, IndexError) as err:
            _LOGGER.debug("dataESP32 unavailable: %s", err)

        return data

    # ---------------------------------------------------------------- write
    async def async_force_action(self, num_action: int, force_minutes: int) -> None:
        """Force an action: +N = on for N min, -N = off for N min, 0 = back to auto.

        (official /ForceAction handler: LesActions[NumAction].tOnOff = Force)
        """
        await self._get(f"/ForceAction?NumAction={int(num_action)}&Force={int(force_minutes)}")

    async def async_update_pid(self, i_act: int, kp: int, ki: int, kd: int) -> None:
        """Real-time PID coefficients (/UpdateK). Not persisted across reboots."""
        await self._get(
            f"/UpdateK?iAct={int(i_act)}&Kp={int(kp)}&Ki={int(ki)}&Kd={int(kd)}"
        )

    async def async_patch_config(self, mutate: Callable[[dict], None]) -> None:
        """Read the full config (/ParaFixe), apply `mutate(config)` in place, post it back (/ParaNew).

        Changes ANY persistent setting (waveform, thresholds, persisted PID, GPIOs…) exactly
        like the "Save" button of the router's web UI. Serialised by a lock.
        """
        async with self._write_lock:
            config = await self.async_get_config()
            mutate(config)
            body = json.dumps(config, separators=(",", ":"))
            await self._post_plain("/ParaNew", body)
