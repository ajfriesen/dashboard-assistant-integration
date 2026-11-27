"""Coordinator: SSE push with a periodic poll fallback."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
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
        self._reload_scheduled = False

    @property
    def node_id(self) -> str:
        """Stable device id, the HA device identifier."""
        return self.info["node_id"]

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll fallback (also the initial refresh)."""
        try:
            return await self.client.async_get_state()
        except DashboardAssistantAuthError as err:
            # Not reauth: nobody can type the device's token (see async_setup_entry).
            raise ConfigEntryError(str(err)) from err
        except DashboardAssistantError as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def async_update_listeners(self) -> None:
        """Hand entities the new snapshot, then catch up with an OS update."""
        super().async_update_listeners()
        self._reload_after_os_update()

    @callback
    def _reload_after_os_update(self) -> None:
        """Reload the entry once the device runs another release than at setup.

        The device's version and capabilities (self.info) are read once, at
        setup, and decide which entities exist. An OS update changes them while
        Home Assistant keeps running, so without a reload it went on showing the
        old version and none of the new entities. Every OS release reports the
        running version in each snapshot, from the same source as the info's.
        """
        running = ((self.data or {}).get("update") or {}).get("installed_version")
        if self._reload_scheduled or not running or running == self.info.get("version"):
            return
        LOGGER.info(
            "Device now runs %s (was %s at setup); reloading to pick up its changes",
            running,
            self.info.get("version"),
        )
        self._reload_scheduled = True
        self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)

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
                # A bad token won't fix itself; the poll path reports it.
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
