# Dashboard Assistant — Home Assistant integration

A first-party Home Assistant integration for [Dashboard Assistant OS][os] kiosks.
It talks to the on-device daemon over an authenticated LAN API (HTTP + Server-Sent
Events), so there is **no MQTT broker to run** — the device is discovered over
mDNS and controlled directly.

## What you get

The kiosk appears in Home Assistant as a single device with:

- **Light** — the display: on/off (DPMS) plus brightness (backlight).
- **Select** — jump to any configured page.
- **Buttons** — next/previous page, reboot, shut down, take screenshot.
- **Text** — ten editable "Page N" slots (`Name | URL`) to manage the page list.
- **Number** — browser zoom (25–400 %).
- **Switch** — dark mode.
- **Update** — OS release, with an Install button on images that can self-update.
- **Image** — the latest screenshot.
- **Sensors** — seconds since last touch, memory, storage, generations, CPU,
  uptime, IP, hostname, model, serial, and (where present) battery and
  temperature.

State updates arrive instantly over the SSE push stream, with a periodic poll as
a fallback (`local_push`).

## Installation (HACS)

1. In HACS, add this repository as a **custom repository** (category: *Integration*):
   `https://github.com/ajfriesen/dashboard-assistant`.
2. Install **Dashboard Assistant** and restart Home Assistant.
3. Home Assistant should auto-discover the kiosk over mDNS — or add it manually
   via **Settings → Devices & services → Add integration → Dashboard Assistant**.
4. When prompted, enter the **API token** shown on the device's
   **Config → Info** screen (and the host/port if adding manually — the API
   defaults to port `8081`).

## Manual installation

Copy `custom_components/dashboard_assistant` into your Home Assistant
`config/custom_components/` directory and restart.

## How it connects

The daemon exposes `http://<device>:8081/api/ha/*`, guarded by a bearer token.
The token is generated on the device on first boot (or seeded/imported) and shown
on the on-screen Config panel. See the OS repo (`daemon/ha.go`,
`modules/core/ha-api.nix`) for the device side.

[os]: https://github.com/ajfriesen/dashboard-assistant
