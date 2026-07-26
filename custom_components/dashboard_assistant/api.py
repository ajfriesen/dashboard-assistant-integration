"""HTTP + SSE client for the Dashboard Assistant daemon API (daemon/ha.go)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from .const import LOGGER


class DashboardAssistantError(Exception):
    """Base error talking to the daemon."""


class DashboardAssistantAuthError(DashboardAssistantError):
    """The bearer token was rejected (HTTP 401)."""


class DashboardAssistantConnectionError(DashboardAssistantError):
    """The daemon could not be reached."""


class DashboardAssistantPairingClosedError(DashboardAssistantError):
    """The device is not currently in pairing mode (HTTP 403)."""


async def async_identify(
    session: aiohttp.ClientSession, host: str, port: int
) -> dict[str, Any]:
    """Fetch the device's stable identity (``node_id`` + ``name``).

    Unauthenticated and side-effect free — the config flow calls it during
    zeroconf discovery to key on a stable id instead of the IP, so one device is
    one Home Assistant entry regardless of address (or a later DHCP change).
    """
    url = f"http://{host}:{port}/api/ha/identify"
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise DashboardAssistantError(f"HTTP {resp.status}: {text.strip()}")
            return await resp.json()
    except aiohttp.ClientError as err:
        raise DashboardAssistantConnectionError(str(err)) from err


async def async_pair(
    session: aiohttp.ClientSession, host: str, port: int
) -> dict[str, Any]:
    """Fetch the API token from a device whose pairing window is open.

    The daemon returns the token (plus ``node_id`` and ``name``) only while the
    operator has pressed *Pair* on the device's Config screen — or the build
    auto-confirms — so no one has to read or type it. The call carries no auth: the
    gate is the pairing window, not a token the caller does not yet have. Raises
    :class:`DashboardAssistantPairingClosedError` when the window is closed.
    """
    url = f"http://{host}:{port}/api/ha/pair"
    try:
        async with session.post(
            url, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status == 403:
                raise DashboardAssistantPairingClosedError("pairing window not open")
            if resp.status >= 400:
                text = await resp.text()
                raise DashboardAssistantError(f"HTTP {resp.status}: {text.strip()}")
            return await resp.json()
    except aiohttp.ClientError as err:
        raise DashboardAssistantConnectionError(str(err)) from err


class DashboardAssistantClient:
    """Thin async wrapper over the daemon's authenticated LAN API.

    All state-changing commands (display/page/zoom/theme) return the full state
    snapshot the daemon computes after applying them, so callers can push it
    straight into the coordinator for instant feedback.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        token: str,
    ) -> None:
        self._session = session
        self._host = host
        self._port = port
        self._base = f"http://{host}:{port}/api/ha"
        self._headers = {"Authorization": f"Bearer {token}"}

    @property
    def events_url(self) -> str:
        """URL of the SSE stream."""
        return f"{self._base}/events"

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self._base}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    raise DashboardAssistantAuthError("invalid API token")
                if resp.status >= 400:
                    text = await resp.text()
                    raise DashboardAssistantError(f"HTTP {resp.status}: {text.strip()}")
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.read()
        except aiohttp.ClientError as err:
            raise DashboardAssistantConnectionError(str(err)) from err

    async def async_get_info(self) -> dict[str, Any]:
        """Device identity + capabilities. Also validates the token."""
        return await self._request("GET", "/info")

    async def async_get_state(self) -> dict[str, Any]:
        """Full state snapshot."""
        return await self._request("GET", "/state")

    async def async_kiosk_login(
        self, token: str, ha_url: str | None = None
    ) -> dict[str, Any]:
        """Stage a Home Assistant login on the device.

        Hands the kiosk a long-lived access token (and optionally the dashboard
        URL) so its browser signs in automatically — no one has to type HA
        credentials on the device. The daemon persists it and relaunches the
        kiosk.
        """
        payload: dict[str, Any] = {"token": token}
        if ha_url:
            payload["ha_url"] = ha_url
        return await self._request("POST", "/kiosk_login", payload)

    async def async_set_display(
        self, *, on: bool | None = None, brightness: int | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if on is not None:
            payload["on"] = on
        if brightness is not None:
            payload["brightness"] = brightness
        return await self._request("POST", "/display", payload)

    async def async_set_page(
        self, *, select: str | None = None, direction: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if select is not None:
            payload["select"] = select
        if direction is not None:
            payload["dir"] = direction
        return await self._request("POST", "/page", payload)

    async def async_set_page_slot(self, index: int, value: str) -> dict[str, Any]:
        return await self._request("POST", "/page_slot", {"index": index, "value": value})

    async def async_set_zoom(self, percent: int) -> dict[str, Any]:
        return await self._request("POST", "/zoom", {"percent": percent})

    async def async_set_theme(self, dark: bool) -> dict[str, Any]:
        return await self._request("POST", "/theme", {"dark": dark})

    async def async_power(self, action: str) -> None:
        await self._request("POST", "/power", {"action": action})

    async def async_install_update(self) -> None:
        await self._request("POST", "/update")

    async def async_take_screenshot(self) -> None:
        await self._request("POST", "/screenshot")

    async def async_get_screenshot(self) -> bytes:
        """Fetch the latest captured screenshot as raw JPEG bytes."""
        return await self._request("GET", "/screenshot.jpg")

    async def async_stream_events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield state snapshots from the SSE stream until the connection drops.

        Keep-alive comment lines (starting with ``:``) are ignored. Each event is
        a single-line ``data:`` payload carrying a full snapshot.
        """
        async with self._session.get(
            self.events_url,
            headers={**self._headers, "Accept": "text/event-stream"},
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=60),
        ) as resp:
            if resp.status == 401:
                raise DashboardAssistantAuthError("invalid API token")
            resp.raise_for_status()
            async for raw in resp.content:
                line = raw.decode("utf-8", "replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if not data:
                    continue
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    LOGGER.debug("dropping malformed SSE frame: %s", data)
