"""Coordinator: SSE push with a periodic poll fallback."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    DashboardAssistantAuthError,
    DashboardAssistantClient,
    DashboardAssistantError,
)
from .const import DOMAIN, LOGGER, POLL_INTERVAL

type DashboardAssistantConfigEntry = ConfigEntry[DashboardAssistantCoordinator]


class DashboardAssistantCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the latest device snapshot, refreshed by SSE and a poll fallback."""

    config_entry: DashboardAssistantConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: DashboardAssistantConfigEntry,
        client: DashboardAssistantClient,
        info: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self.info = info
        self._sse_task: asyncio.Task[None] | None = None

    @property
    def node_id(self) -> str:
        """Stable device id, the HA device identifier."""
        return self.info["node_id"]

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll fallback (also the initial refresh)."""
        try:
            return await self.client.async_get_state()
        except DashboardAssistantAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DashboardAssistantError as err:
            raise UpdateFailed(str(err)) from err

    def start_stream(self) -> None:
        """Launch the background SSE loop tied to the config entry's lifetime."""
        if self._sse_task is None:
            self._sse_task = self.config_entry.async_create_background_task(
                self.hass, self._stream_loop(), name=f"{DOMAIN}_sse"
            )

    async def _stream_loop(self) -> None:
        """Consume the SSE stream forever, reconnecting with backoff."""
        backoff = 1
        while True:
            try:
                async for snapshot in self.client.async_stream_events():
                    self.async_set_updated_data(snapshot)
                    backoff = 1
            except DashboardAssistantAuthError:
                # A bad token won't fix itself; let the poll path raise reauth.
                LOGGER.warning("SSE stream rejected the token; falling back to polling")
                return
            except Exception as err:  # noqa: BLE001
                LOGGER.debug("SSE stream ended (%s); reconnecting in %ss", err, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    def apply_snapshot(self, snapshot: Any) -> None:
        """Push a snapshot returned by a command straight to entities."""
        if isinstance(snapshot, dict) and "device" in snapshot:
            self.async_set_updated_data(snapshot)
