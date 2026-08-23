#!/bin/bash

set -u

CHROME="${TEDDY_CHROME_BIN:-/opt/teddy-browser/chrome/chrome}"
EXTENSION="${TEDDY_EXTENSION_DIR:-/opt/teddy-browser/extension}"
PROFILE="${TEDDY_PROFILE_DIR:-/config/chrome-profile}"

mkdir -p "${PROFILE}"

ARGS=(
  --no-sandbox
  --ozone-platform=wayland
  --user-data-dir="${PROFILE}"
  --no-first-run
  --no-default-browser-check
  --disable-session-crashed-bubble
  --disable-infobars
  --load-extension="${EXTENSION}"
  --start-maximized
)

if [ -n "${TEDDY_PROXY_SERVER:-}" ]; then
  ARGS+=(--proxy-server="${TEDDY_PROXY_SERVER}")
fi

exec "${CHROME}" "${ARGS[@]}" "${TEDDY_START_URL:-about:blank}"
