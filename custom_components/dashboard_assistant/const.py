"""Constants for the Dashboard Assistant integration."""

from __future__ import annotations

import logging
from datetime import timedelta

DOMAIN = "dashboard_assistant"
LOGGER = logging.getLogger(__package__)

DEFAULT_PORT = 8081

# mDNS service the device advertises (see modules/core/ha-api.nix).
ZEROCONF_TYPE = "_dashboard-assistant._tcp.local."

# Fixed number of editable "Page N" text slots the daemon exposes (mirrors
# pageSlots in daemon/pages.go).
PAGE_SLOTS = 10

MANUFACTURER = "Dashboard Assistant"

# Auto-provisioned kiosk login. The integration creates a dedicated Home Assistant
# user and a long-lived token, then hands it to the device so its browser signs in
# without anyone typing credentials on the kiosk. These keys record what was
# created, in the config entry data, so provisioning is idempotent across restarts
# and the user can be cleaned up when the integration is removed.
#
# Every tablet's user shares this one display name (HA token-users have a single
# visible name); the per-device long-lived token is labelled with the MAC instead,
# so tablets stay distinguishable in the user's token list.
KIOSK_USER_NAME = "Dashboard Assistant"
CONF_KIOSK_USER_ID = "kiosk_user_id"
CONF_KIOSK_REFRESH_TOKEN_ID = "kiosk_refresh_token_id"

# Poll fallback interval. The primary update path is the SSE push stream; this
# is a safety net in case the stream drops without the socket erroring.
POLL_INTERVAL = timedelta(seconds=60)
