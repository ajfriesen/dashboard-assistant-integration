"""Base entity for Dashboard Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import DashboardAssistantCoordinator


class DashboardAssistantEntity(CoordinatorEntity[DashboardAssistantCoordinator]):
    """Common device wiring for every Dashboard Assistant entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DashboardAssistantCoordinator, key: str) -> None:
        super().__init__(coordinator)
        info = coordinator.info
        node_id = coordinator.node_id
        self._attr_unique_id = f"{node_id}_{key}"

        connections = set()
        if mac := info.get("mac"):
            connections.add((CONNECTION_NETWORK_MAC, mac))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, node_id)},
            name=info.get("name") or "Dashboard Assistant",
            manufacturer=MANUFACTURER,
            model=info.get("model") or "kiosk",
            sw_version=info.get("version"),
            serial_number=info.get("serial") or None,
            connections=connections,
        )

    @property
    def data(self) -> dict[str, Any]:
        """The latest full snapshot."""
        return self.coordinator.data

    async def _run_command(self, snapshot: Any) -> None:
        """Push a command's returned snapshot to the coordinator (instant update)."""
        self.coordinator.apply_snapshot(snapshot)
