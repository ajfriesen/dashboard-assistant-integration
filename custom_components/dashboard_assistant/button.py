"""Buttons: page navigation, power, screenshot."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import DashboardAssistantClient
from .coordinator import DashboardAssistantConfigEntry, DashboardAssistantCoordinator
from .entity import DashboardAssistantEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DashboardAssistantButtonDescription(ButtonEntityDescription):
    """Describes a button and the command it fires."""

    press_fn: Callable[[DashboardAssistantClient], Awaitable[object]]
    warning: str | None = None
    """Logged before the command fires, for destructive actions."""


BUTTONS: tuple[DashboardAssistantButtonDescription, ...] = (
    DashboardAssistantButtonDescription(
        key="page_next",
        name="Next page",
        icon="mdi:arrow-right-bold",
        press_fn=lambda client: client.async_set_page(direction="next"),
    ),
    DashboardAssistantButtonDescription(
        key="page_prev",
        name="Previous page",
        icon="mdi:arrow-left-bold",
        press_fn=lambda client: client.async_set_page(direction="prev"),
    ),
    DashboardAssistantButtonDescription(
        key="reboot",
        name="Reboot",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda client: client.async_power("reboot"),
    ),
    DashboardAssistantButtonDescription(
        key="shutdown",
        name="Shut down",
        icon="mdi:power",
        press_fn=lambda client: client.async_power("shutdown"),
    ),
    DashboardAssistantButtonDescription(
        key="screenshot_take",
        name="Take screenshot",
        icon="mdi:camera",
        press_fn=lambda client: client.async_take_screenshot(),
    ),
    DashboardAssistantButtonDescription(
        key="factory_reset",
        name="Factory reset",
        icon="mdi:restore-alert",
        press_fn=lambda client: client.async_reset(),
        warning=(
            "Factory reset requested: the device will clear its provisioning and "
            "regenerate its API token on reboot. This config entry will stop "
            "working and must be removed and the device re-added."
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        DashboardAssistantButton(coordinator, description) for description in BUTTONS
    )


class DashboardAssistantButton(DashboardAssistantEntity, ButtonEntity):
    """A command button."""

    entity_description: DashboardAssistantButtonDescription

    def __init__(
        self,
        coordinator: DashboardAssistantCoordinator,
        description: DashboardAssistantButtonDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        if self.entity_description.warning:
            _LOGGER.warning(self.entity_description.warning)
        result = await self.entity_description.press_fn(self.coordinator.client)
        # Page navigation returns a snapshot; power/screenshot do not.
        self.coordinator.apply_snapshot(result)
