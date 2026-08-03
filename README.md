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

This integration isn't in the default HACS store, so it's added as a **custom
repository**. You only do this once; updates then show up in HACS like any other.

### Prerequisites

- A running Home Assistant instance you can reach in a browser.
- [HACS](https://hacs.xyz/) installed and set up. If you don't have it yet,
  follow the official [HACS installation guide](https://hacs.xyz/docs/use/download/download/).

### 1. Add the custom repository

1. In Home Assistant, open **HACS** from the sidebar.
2. Click the **⋮** menu in the top-right corner and choose **Custom repositories**.
3. In the **Repository** field, paste:

   ```
   https://github.com/ajfriesen/dashboard-assistant-integration
   ```

4. Set **Type** (or **Category**) to **Integration**.
5. Click **Add**, then close the dialog.

### 2. Install the integration

1. Back in HACS, search for **Dashboard Assistant**.
2. Open it and click **Download** (choose the latest version).
3. **Restart Home Assistant** when prompted
   (**Settings → System → Restart**). HACS only copies the files; Home
   Assistant loads the integration on restart.

### 3. Add the device

After the restart, Home Assistant should **auto-discover** the kiosk over mDNS —
you'll see a "Dashboard Assistant" discovered card under
**Settings → Devices & services**. If it doesn't appear, add it manually:

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **Dashboard Assistant** and select it.
3. Enter the connection details:
   - **API token** — shown on the device's **Config → Info** screen.
   - **Host / port** (manual setup only) — the device's IP or hostname; the API
     defaults to port **8081**.
4. Submit. The kiosk appears as a single device with all its entities.

### Updating

When a new release is published, HACS shows an update on the **Dashboard
Assistant** card. Click **Update**, then restart Home Assistant.

## Manual installation

If you'd rather not use HACS, copy the integration in by hand:

1. Copy the `custom_components/dashboard_assistant` folder from this repository
   into your Home Assistant `config/custom_components/` directory (create the
   `custom_components` folder if it doesn't exist).
2. Restart Home Assistant.
3. Add the device as described in [step 3](#3-add-the-device) above.

## How it connects

The daemon exposes `http://<device>:8081/api/ha/*`, guarded by a bearer token.
The token is generated on the device on first boot (or seeded/imported) and shown
on the on-screen Config panel. See the OS repo (`daemon/ha.go`,
`modules/core/ha-api.nix`) for the device side.

[os]: https://github.com/ajfriesen/dashboard-assistant
