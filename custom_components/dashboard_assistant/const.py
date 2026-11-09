"""Constants for the Dashboard Assistant integration."""

from __future__ import annotations

import logging
from datetime import timedelta

DOMAIN = "dashboard_assistant"
LOGGER = logging.getLogger(__package__)

DEFAULT_PORT = 8081

# mDNS service the device advertises (see modules/core/ha-api.nix).
ZEROCONF_TYPE = "_dashboard-assistant._tcp.local."

MANUFACTURER = "Dashboard Assistant"

# Auto-provisioned kiosk login. The integration creates a dedicated Home Assistant
# user and a long-lived token, then hands it to the device so its browser signs in
# without anyone typing credentials on the kiosk. These keys record what was
# created, in the config entry data, so provisioning is idempotent across restarts
# and the user can be cleaned up when the integration is removed.
#
# Base display name for the per-tablet kiosk user. provision.py names each user
# after the device itself ("Dashboard Assistant (45299a)", matching the HA device
# card) so displays are distinguishable in HA's user list, using this as the
# fallback base when the device reports no name; the token carries the same label.
KIOSK_USER_NAME = "Dashboard Assistant"
CONF_KIOSK_USER_ID = "kiosk_user_id"
CONF_KIOSK_REFRESH_TOKEN_ID = "kiosk_refresh_token_id"
# Set once the login has actually been pushed to the device. Distinct from
# CONF_KIOSK_USER_ID (recorded as soon as the HA user is created, before the
# push) so the self-healing retry knows whether the device itself is signed in,
# not just whether the HA-side user exists.
CONF_KIOSK_PROVISIONED = "kiosk_provisioned"
# The two URLs that login carried: Home Assistant's own URL, which the device
# signs in on, and the device's home (see CONF_HOME). Either can change (the
# option, or the URL in Home Assistant's network settings), and when the URLs
# Home Assistant would send now differ from these, the login is pushed again.
CONF_KIOSK_URL = "kiosk_url"
CONF_KIOSK_HOME_URL = "kiosk_home_url"

# SHA-256 of the device's TLS certificate, pinned when the device pairs; every
# authenticated call is made over TLS against it (see pin_for in api.py). Not a
# secret: it is a hash of a certificate the device shows to anyone who connects,
# so it stays visible in diagnostics, where it is the first thing worth seeing
# when a device stops connecting after a reset.
CONF_CERT_FINGERPRINT = "cert_fingerprint"

# Poll fallback interval. The primary update path is the SSE push stream; this
# is a safety net in case the stream drops without the socket erroring.
POLL_INTERVAL = timedelta(seconds=60)

# Options: the device's home, where it starts and where its Home button goes.
# DEFAULT_HOME means Home Assistant's own default dashboard, i.e. its bare URL.
# Anything else is a path on Home Assistant (a dashboard's url_path, or
# "<url_path>/<view>" for one of its tabs) or, when it has a scheme, any
# website. Not "": the frontend's select can read an empty value as nothing
# chosen. No dashboard can be called "default": Home Assistant requires a hyphen
# in the url_path of a dashboard a user creates, and its built-in ones are named
# for what they show (lovelace, map, energy, ...).
CONF_HOME = "home"
DEFAULT_HOME = "default"

# The pages field of the options form: a list of {"name", "url"}. Never stored
# in the entry; the device owns its page list (see DashboardAssistantOptionsFlow).
CONF_PAGES = "pages"
