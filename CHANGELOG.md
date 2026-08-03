# Changelog

This file is generated from [Conventional Commit](https://www.conventionalcommits.org/)
messages by [release-please](https://github.com/googleapis/release-please). New
versions are added above automatically when a release PR is merged — write clear
commit messages rather than editing released sections by hand.

`0.1.0` is the documented starting point; automated releases begin with the next
version.

## [0.1.0-rc.1](https://github.com/ajfriesen/dashboard-assistant-integration/compare/v0.1.0...v0.1.0-rc.1) (2026-08-03)


### Miscellaneous Chores

* release 0.1.0-rc.1 ([bd8e02e](https://github.com/ajfriesen/dashboard-assistant-integration/commit/bd8e02ecc66b812710f181dcea8be74ddc226334))

## [0.1.0] - 2026-08-03

### Added

- Initial Home Assistant integration for Dashboard Assistant kiosks: mDNS
  auto-discovery and a guided config flow (device pairing / API token).
- **Rotation** select to turn the display 0 / 90 / 180 / 270°.
- Display **light** (power + brightness) and **Zoom** number.
- **Dark mode** switch to flip the Home Assistant frontend theme.
- **Page** select, editable page-URL **text** slots, and next/previous page
  **buttons** to drive the kiosk's dashboard list.
- **Screenshot** button + image to capture the current view on demand.
- **Reboot**, **shut down**, and **update** controls.
- Battery, temperature, CPU, memory and storage **sensors**.
