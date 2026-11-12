"""Dark-mode, Sendspin player, screen saver and VNC switches."""

from __future__ import annotations

from datetime import UTC, datetime
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
    # Older OS builds have no screen saver; create nothing rather than a dead switch.
    if "screensaver" in coordinator.data:
        entities.append(ScreensaverSwitch(coordinator))
    if "vnc" in coordinator.data:
        entities.append(VncSwitch(coordinator))
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


class ScreensaverSwitch(DashboardAssistantEntity, SwitchEntity):
    """ON shows the selected screen saver now, OFF dismisses it.

    It also turns on by itself after the idle timeout, and off when someone
    touches the screen.
    """

    _attr_name = "Screen saver"
    _attr_icon = "mdi:monitor-star"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "screensaver")

    @property
    def is_on(self) -> bool:
        return bool(self.data["screensaver"]["active"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_screensaver(active=True)
        await self._run_command(snapshot)

    async def async_turn_off(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_screensaver(active=False)
        await self._run_command(snapshot)


class VncSwitch(DashboardAssistantEntity, SwitchEntity):
    """ON starts a VNC server on the device for remote access to the kiosk.

    The device makes a new password every time this turns on and closes the
    server by itself after the VNC timeout. The attributes say how to connect.
    The password is left out of the recorder: it is a secret, and a stored one
    would outlive its session in the history.
    """

    _attr_name = "VNC"
    _attr_icon = "mdi:remote-desktop"
    _unrecorded_attributes = frozenset({"password"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "vnc")

    @property
    def is_on(self) -> bool:
        return bool(self.data["vnc"]["on"])

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        vnc = self.data["vnc"]
        if not vnc.get("on"):
            return None
        host = self.coordinator.client.host
        if ":" in host:  # IPv6
            host = f"[{host}]"
        attrs: dict[str, Any] = {
            "address": f"{host}:{vnc['port']}",
            "username": vnc.get("username"),
            "password": vnc.get("password"),
        }
        if closes_at := vnc.get("closes_at"):
            attrs["closes_at"] = datetime.fromtimestamp(closes_at, UTC).isoformat()
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_vnc(on=True)
        await self._run_command(snapshot)

    async def async_turn_off(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_vnc(on=False)
        await self._run_command(snapshot)
