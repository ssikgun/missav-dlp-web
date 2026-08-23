#!/bin/bash

set -u

CHROME="${TEDDY_CHROME_BIN:-/opt/teddy-browser/chrome/chrome}"
EXTENSION="${TEDDY_EXTENSION_DIR:-/opt/teddy-browser/extension}"
PROFILE="${TEDDY_PROFILE_DIR:-/config/chrome-profile}"

mkdir -p "${PROFILE}"

cleanup_stale_singleton() {
  local lock="${PROFILE}/SingletonLock"
  local target=""
  local lock_host=""
  local lock_pid=""
  local current_host=""
  local cmdline=""

  [ -L "${lock}" ] || return 0

  target="$(readlink "${lock}" 2>/dev/null || true)"
  current_host="$(hostname)"

  lock_host="${target%-*}"
  lock_pid="${target##*-}"

  if [ -z "${target}" ] || \
     [ "${lock_host}" = "${target}" ] || \
     ! [[ "${lock_pid}" =~ ^[0-9]+$ ]]
  then
    echo "WARNING: unrecognized Chromium SingletonLock; leaving it untouched: ${target}" >&2
    return 0
  fi

  if [ "${lock_host}" != "${current_host}" ]; then
    echo "Removing stale Chromium Singleton lock from previous container: ${target}"

  elif [ ! -r "/proc/${lock_pid}/cmdline" ]; then
    echo "Removing stale Chromium Singleton lock for dead PID ${lock_pid}"

  else
    cmdline="$(tr '\0' ' ' < "/proc/${lock_pid}/cmdline" 2>/dev/null || true)"

    if [[ "${cmdline}" == *"${CHROME}"* ]] && \
       [[ "${cmdline}" == *"--user-data-dir=${PROFILE}"* ]]
    then
      echo "Chromium profile is already active in this container (PID ${lock_pid}); keeping lock." >&2
      return 0
    fi

    echo "Removing stale Chromium Singleton lock held by unrelated PID ${lock_pid}"
  fi

  rm -f \
    "${PROFILE}/SingletonLock" \
    "${PROFILE}/SingletonCookie" \
    "${PROFILE}/SingletonSocket"
}

cleanup_stale_singleton

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
