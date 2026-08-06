"""Page, display-rotation, and OS version selectors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the page, rotation, and version selectors."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [
        PageSelect(coordinator),
        RotationSelect(coordinator),
    ]
    # The version picker only makes sense where the image can apply switches (the
    # persistent disk / SD targets, not the ephemeral ISO), matching how the
    # update entity gates its Install button.
    if coordinator.data["update"].get("installable"):
        entities.append(TargetVersionSelect(coordinator))
    async_add_entities(entities)


class PageSelect(DashboardAssistantEntity, SelectEntity):
    """Jump the kiosk to one of the configured pages."""

    _attr_name = "Page"
    _attr_icon = "mdi:web"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "page")

    @property
    def options(self) -> list[str]:
        return list(self.data["page"]["options"])

    @property
    def current_option(self) -> str | None:
        return self.data["page"]["current"] or None

    async def async_select_option(self, option: str) -> None:
        snapshot = await self.coordinator.client.async_set_page(select=option)
        await self._run_command(snapshot)


class RotationSelect(DashboardAssistantEntity, SelectEntity):
    """Rotate the kiosk display to one of 0/90/180/270°.

    The daemon reports the current angle and the supported angles as integer
    degrees (see daemon/rotation.go); we render them with a degree sign for the
    dropdown and strip it back to an int when a choice is picked.
    """

    _attr_name = "Rotation"
    _attr_icon = "mdi:screen-rotation"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "rotation")

    @property
    def options(self) -> list[str]:
        return [f"{deg}°" for deg in self.data["rotation"]["options"]]

    @property
    def current_option(self) -> str | None:
        return f"{self.data['rotation']['current']}°"

    async def async_select_option(self, option: str) -> None:
        degrees = int(option.rstrip("°"))
        snapshot = await self.coordinator.client.async_set_rotation(degrees)
        await self._run_command(snapshot)


def _strip_v(tag: str) -> str:
    """Drop a single leading v/V so a tag compares against the plain installed
    version the daemon reports (mirrors normalizeVersion in daemon/update.go)."""
    if len(tag) > 1 and tag[0] in ("v", "V"):
        return tag[1:]
    return tag


class TargetVersionSelect(DashboardAssistantEntity, SelectEntity):
    """Install any released OS version, newer or older, from a single dropdown.

    The daemon reports the recent releases (stable and prerelease) as
    ``update.available`` — each an ``{tag, name, prerelease}`` entry, newest
    first (see daemon/update.go). We render one option per release, marking
    prereleases, and install the picked tag immediately. Downgrades are allowed:
    the list is not filtered by the installed version, and NixOS switches to the
    chosen tag either way (a bad image is caught by boot-assessment rollback).
    """

    _attr_name = "Target version"
    _attr_icon = "mdi:package-variant"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "target_version")

    @property
    def _available(self) -> list[dict[str, Any]]:
        return self.data["update"].get("available") or []

    def _label(self, entry: dict[str, Any]) -> str:
        """A unique, stable dropdown label for a release (tags are unique)."""
        tag = entry.get("tag", "")
        return f"{tag} (pre-release)" if entry.get("prerelease") else tag

    @property
    def options(self) -> list[str]:
        return [self._label(entry) for entry in self._available]

    @property
    def current_option(self) -> str | None:
        installed = self.data["update"].get("installed_version")
        for entry in self._available:
            if _strip_v(entry.get("tag", "")) == installed:
                return self._label(entry)
        return None

    async def async_select_option(self, option: str) -> None:
        # Map the chosen label back to its exact tag; ignore an unknown label
        # rather than guessing a ref to build.
        tag = next(
            (e.get("tag") for e in self._available if self._label(e) == option),
            None,
        )
        if tag is None:
            return
        await self.coordinator.client.async_install_version(tag)
        await self.coordinator.async_request_refresh()
