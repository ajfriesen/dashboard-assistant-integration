![GitHub commit activity](https://img.shields.io/github/commit-activity/m/ajfriesen/dashboard-assistant-integration)

# Dashboard Assistant Integration

A Home Assistant integration for [Dashboard Assistant](https://dashboardassistant.org/) kiosks operating system.
This lets you discover and provision tablets with just one click in Home Assistant.
No complex setups, just a click.

## What you get

The easiest Home Assistant Kiosk setup.
The tablet appears as a Home Assistant device and can be controlled:

- **Light** — the display: on/off (DPMS) plus brightness (backlight).
- **Select** — jump to any configured page.
- **Buttons** — next/previous page, reboot, shut down, take screenshot.
- **Select** — screen saver style (whatever the OS ships, e.g. clock, logo).
- **Number** — browser zoom (25–400 %), and the screen saver timeout
  (minutes without a touch, 0–240; 0 turns the idle trigger off).
- **Switch** — dark mode, and the screen saver (on shows it now, off
  dismisses it; it also follows the idle timeout and touches).
- **Update** — OS release, with an Install button on images that can self-update.
- **Image** — the latest screenshot.
- **Sensors** — seconds since last touch, memory, storage, generations, CPU,
  uptime, IP, hostname, model, serial, and (where present) battery and
  temperature.

State updates arrive instantly over the SSE push stream, with a periodic poll as a fallback (`local_push`).

## Installation (HACS)

This integration isn't in the default HACS store, so it's added as a **custom repository** yet.
You only do this once; updates then show up in HACS like any other.

Waiting for this PR to get merged.

![GitHub pull request status](https://img.shields.io/github/status/s/pulls/hacs/default/11319)

### Prerequisites

- A running Home Assistant instance you can reach in a browser.
- [HACS](https://hacs.xyz/) installed and set up.
  If you don't have it yet, follow the official [HACS installation guide](https://hacs.xyz/docs/use/download/download/).

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

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ajfriesen&category=integration&repository=dashboard-assistant-integration)

1. Open it and click **Download** (choose the latest version).
2. **Restart Home Assistant** when prompted
   (**Settings → System → Restart**). HACS only copies the files; Home
   Assistant loads the integration on restart.



### 3. Add the device

After the restart, Home Assistant **discovers** the device over mDNS: a
"Dashboard Assistant" card appears under **Settings → Devices & services →
Discovered**. Click **Add**, then **Add** again. The device hands over its API
token by itself, so there is nothing to type, and it appears as a single device
with all its entities.

Discovery is the only way in. If the card does not appear, Home Assistant cannot
see the device's mDNS announcement, usually because the two are on different
networks or VLANs.

A device pairs once. To add it to another Home Assistant, or again after
deleting its entry, factory-reset it from its admin page first. After a factory
reset the old entry stops with an error; delete it, and the device is
discovered again.

### 4. Choose the dashboard and pages

Open **Settings → Devices & services → Dashboard Assistant** and click
**Configure**:

- **Dashboard** — the device shows Home Assistant's default dashboard until you
  pick another. Admin-only dashboards are not listed, because the device signs
  in as a regular user.
- **Pages** — any number of pages, each a name and the address of any website. The
  **Page** select and the next/previous buttons switch between them, in this
  order.

Saving sends both to the device straight away.

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

## Author

This project was created by Andrej Friesen in 2026.

<a href="https://github.com/ajfriesen">
  <img src="https://wsrv.nl/?url=github.com/ajfriesen.png&w=200&h=200&fit=cover&mask=circle" width="100" alt="Andrej Friesen">
</a>