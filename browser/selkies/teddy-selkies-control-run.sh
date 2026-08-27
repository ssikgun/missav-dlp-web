#!/bin/sh

set -eu

case "${TEDDY_SELKIES_CONTROL_ENABLED:-false}" in
  1|true|TRUE|yes|YES)
    ;;
  *)
    exec sleep infinity
    ;;
esac

exec /usr/bin/python3 \
  /opt/teddy-browser/teddy_selkies_control.py
