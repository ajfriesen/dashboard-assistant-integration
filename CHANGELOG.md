# Changelog

This file is generated from [Conventional Commit](https://www.conventionalcommits.org/)
messages by [release-please](https://github.com/googleapis/release-please). New
versions are added above automatically when a release PR is merged — write clear
commit messages rather than editing released sections by hand.

`0.1.0` is the documented starting point; automated releases begin with the next
version.

## [0.2.0-rc.4](https://github.com/ajfriesen/dashboard-assistant-integration/compare/v0.1.0-rc.4...v0.2.0-rc.4) (2026-09-12)


### Features

* **binary_sensor:** filesystem health problem sensor ([284a035](https://github.com/ajfriesen/dashboard-assistant-integration/commit/284a0355becffaf2510c7fdf8207d5f0fc0cf036))
* **binary_sensor:** filesystem health problem sensor ([22f07df](https://github.com/ajfriesen/dashboard-assistant-integration/commit/22f07dfc68b98f1a4074ec6a4016f7c6451ebf36))

## [0.1.0-rc.4](https://github.com/ajfriesen/dashboard-assistant-integration/compare/v0.1.0-rc.3...v0.1.0-rc.4) (2026-08-06)


### Features

* add OS generation sensor with tag label and history ([626f4d5](https://github.com/ajfriesen/dashboard-assistant-integration/commit/626f4d5d37b658f4a73df3d76077cdf68dff580b))
* add Target version selector for installing any OS release ([c8fc481](https://github.com/ajfriesen/dashboard-assistant-integration/commit/c8fc481643b106273e822ab356283faffbd2ab2a))


### Miscellaneous Chores

* release 0.1.0-rc.4 ([7ef7fe0](https://github.com/ajfriesen/dashboard-assistant-integration/commit/7ef7fe0348a8c8cfaa4d68b73b76ac04ca038c16))

## [0.1.0-rc.3](https://github.com/ajfriesen/dashboard-assistant-integration/compare/v0.1.0-rc.2...v0.1.0-rc.3) (2026-08-05)


### Features

* **provision:** self-heal kiosk login and drop the manual button ([bf56fc1](https://github.com/ajfriesen/dashboard-assistant-integration/commit/bf56fc151851afbed57dc55cf70a53fa26b761ae))


### Miscellaneous Chores

* release 0.1.0-rc.3 ([39d3b60](https://github.com/ajfriesen/dashboard-assistant-integration/commit/39d3b60da3149d158c9c3273e18e267fe48a5c77))

## [0.1.0-rc.2](https://github.com/ajfriesen/dashboard-assistant-integration/compare/v0.1.0-rc.1...v0.1.0-rc.2) (2026-08-05)


### Features

* **entities:** surface update, factory reset and kiosk login under Controls ([731f71e](https://github.com/ajfriesen/dashboard-assistant-integration/commit/731f71e47a1cfd9a46208ecfef7089b12a7365a0))


### Bug Fixes

* **provision:** always suffix the kiosk user with a per-device id ([d1902b7](https://github.com/ajfriesen/dashboard-assistant-integration/commit/d1902b72933ca3f7a32c1274aac149ccb7199566))


### Miscellaneous Chores

* release 0.1.0-rc.2 ([f0ffe9f](https://github.com/ajfriesen/dashboard-assistant-integration/commit/f0ffe9f2fb7f5fc71aeb128ba0159e85a64e96ea))

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
