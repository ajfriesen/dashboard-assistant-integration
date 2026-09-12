"""Dark-mode and Sendspin player switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches, adding Sendspin only on devices that ship the player."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [DarkModeSwitch(coordinator)]
    if coordinator.info.get("has_sendspin") or coordinator.data.get("sendspin"):
        entities.append(SendspinSwitch(coordinator))
    async_add_entities(entities)


class DarkModeSwitch(DashboardAssistantEntity, SwitchEntity):
    """ON drives the frontend into its dark theme, OFF back to light."""

    _attr_name = "Dark mode"
    _attr_icon = "mdi:theme-light-dark"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "theme")

    @property
    def is_on(self) -> bool:
        return bool(self.data["theme"]["dark"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_theme(True)
        await self._run_command(snapshot)

    async def async_turn_off(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_theme(False)
        await self._run_command(snapshot)


class SendspinSwitch(DashboardAssistantEntity, SwitchEntity):
    """ON makes the device a Sendspin player — a speaker for Music Assistant."""

    _attr_name = "Sendspin player"
    _attr_icon = "mdi:speaker-multiple"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "sendspin")

    @property
    def is_on(self) -> bool:
        sendspin = self.data.get("sendspin") or {}
        return bool(sendspin.get("on"))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose systemd's view, so a player that is on but crash-looping shows
        `status: failed` instead of a contented ON."""
        sendspin = self.data.get("sendspin") or {}
        status = sendspin.get("state")
        return {"status": status} if status else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_sendspin(True)
        await self._run_command(snapshot)

    async def async_turn_off(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_sendspin(False)
        await self._run_command(snapshot)
