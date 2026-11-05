"""Buttons: page navigation, power, screenshot, recovery."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import DashboardAssistantClient
from .const import DOMAIN
from .coordinator import DashboardAssistantConfigEntry, DashboardAssistantCoordinator
from .entity import DashboardAssistantEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DashboardAssistantButtonDescription(ButtonEntityDescription):
    """Describes a button and the command it fires."""

    press_fn: Callable[[DashboardAssistantClient, dict[str, Any]], Awaitable[object]]
    warning: str | None = None
    """Logged before the command fires, for destructive actions."""
    removes_entry: bool = False
    """The command leaves this entry's token useless, so the entry goes too."""


async def _roll_back(client: DashboardAssistantClient, data: dict[str, Any]) -> None:
    generation = _previous_generation(data)
    if generation is None:
        # Refused rather than shown unavailable: unavailable means the device
        # does not answer, and this one does.
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_earlier_generation"
        )
    await client.async_roll_back(generation)


def _previous_generation(data: dict[str, Any]) -> int | None:
    """The newest generation older than the one running, if there is one."""
    generations = data.get("generation_list") or []
    current = next((g["number"] for g in generations if g.get("current")), None)
    if current is None:
        return None
    older = [g["number"] for g in generations if g["number"] < current]
    return max(older, default=None)


BUTTONS: tuple[DashboardAssistantButtonDescription, ...] = (
    DashboardAssistantButtonDescription(
        key="page_next",
        name="Next page",
        icon="mdi:arrow-right-bold",
        press_fn=lambda client, data: client.async_set_page(direction="next"),
    ),
    DashboardAssistantButtonDescription(
        key="page_prev",
        name="Previous page",
        icon="mdi:arrow-left-bold",
        press_fn=lambda client, data: client.async_set_page(direction="prev"),
    ),
    DashboardAssistantButtonDescription(
        key="reboot",
        name="Reboot",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda client, data: client.async_power("reboot"),
    ),
    DashboardAssistantButtonDescription(
        key="shutdown",
        name="Shut down",
        icon="mdi:power",
        press_fn=lambda client, data: client.async_power("shutdown"),
    ),
    DashboardAssistantButtonDescription(
        key="screenshot_take",
        name="Take screenshot",
        icon="mdi:camera",
        press_fn=lambda client, data: client.async_take_screenshot(),
    ),
    DashboardAssistantButtonDescription(
        key="roll_back",
        name="Roll back",
        icon="mdi:history",
        press_fn=_roll_back,
        warning="Roll back requested: the device boots the previous generation.",
    ),
    DashboardAssistantButtonDescription(
        key="factory_reset",
        name="Factory reset",
        icon="mdi:restore-alert",
        press_fn=lambda client, data: client.async_reset(),
        warning=(
            "Factory reset requested: the device clears its provisioning and Wi-Fi "
            "and regenerates its API token. This entry is removed; a wired device "
            "is discovered again on its own, a Wi-Fi one once it has a seed file."
        ),
        removes_entry=True,
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
        description = self.entity_description
        if description.warning:
            _LOGGER.warning(description.warning)
        result = await description.press_fn(
            self.coordinator.client, self.coordinator.data
        )
        if description.removes_entry:
            # The device regenerates its token on reboot, so this entry can never
            # connect again. Removing it lets discovery offer the device afresh.
            entry = self.coordinator.config_entry
            self.hass.async_create_task(
                self.hass.config_entries.async_remove(entry.entry_id)
            )
            return
        # Page navigation returns a snapshot; power/screenshot do not.
        self.coordinator.apply_snapshot(result)
