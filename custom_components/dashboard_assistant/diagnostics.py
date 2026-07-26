"""Diagnostics for a Dashboard Assistant config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant

from .coordinator import DashboardAssistantConfigEntry

TO_REDACT = {CONF_TOKEN, "serial", "mac"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "info": async_redact_data(coordinator.info, TO_REDACT),
        "state": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
