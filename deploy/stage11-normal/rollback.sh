#!/bin/bash
set -euo pipefail
umask 077
stage11_script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$stage11_script_dir/paused-common.sh"
stage11_mode=normal
if [[ "${1:-}" == --paused ]]; then
  stage11_mode=paused
  shift
fi
if [[ "$#" -ne 1 ]]; then
  echo 'Usage: rollback.sh [--paused] BACKUP_DIRECTORY' >&2
  exit 2
fi
stage11_backup="$1"
stage11_deployment=/opt/missav-dlp-web/discovery/stage11-normal-deployment
stage11_systemd_dir=/etc/systemd/system
if [[ "$stage11_mode" == paused ]]; then
  stage11_backup="$(realpath -e -- "$stage11_backup")"
  case "$stage11_backup" in
    "$stage11_deployment"/backups/*) ;;
    *)
      echo 'PAUSED_ROLLBACK=BACKUP_OUTSIDE_DEPLOYMENT' >&2
      exit 1
      ;;
  esac
  stage11_restore_paused_backup "$stage11_backup"
  echo 'PAUSED_ROLLBACK=COMPLETE; timer remains disabled and inactive'
  exit 0
fi
[[ "$stage11_backup" == "$stage11_deployment"/backups/* && -d "$stage11_backup" ]]
if systemctl is-active --quiet teddy-subtitle-normal.service; then
  echo 'ROLLBACK=BLOCKED_ACTIVE_NORMAL_JOB' >&2
  exit 1
fi
systemctl disable --now teddy-subtitle-normal.timer
for stage11_unit in teddy-subtitle-normal.service teddy-subtitle-normal.timer; do
  if [[ -f "$stage11_backup/$stage11_unit" ]]; then
    cp -a "$stage11_backup/$stage11_unit" "/etc/systemd/system/$stage11_unit"
  else
    rm -f "/etc/systemd/system/$stage11_unit"
  fi
done
if [[ -L "$stage11_backup/current" ]]; then
  stage11_current_temp="$stage11_deployment/.current.rollback.$$"
  [[ ! -e "$stage11_current_temp" && ! -L "$stage11_current_temp" ]]
  cp -a -- "$stage11_backup/current" "$stage11_current_temp"
  mv -Tf -- "$stage11_current_temp" "$stage11_deployment/current"
elif [[ -e "$stage11_backup/current" ]]; then
  cp -a --remove-destination "$stage11_backup/current" "$stage11_deployment/current"
else
  rm -f "$stage11_deployment/current"
fi
if [[ -e "$stage11_backup/runtime.env" || -L "$stage11_backup/runtime.env" ]]; then
  cp -a --remove-destination "$stage11_backup/runtime.env" "$stage11_deployment/runtime.env"
else
  rm -f "$stage11_deployment/runtime.env"
fi
systemctl daemon-reload
if [[ -f "$stage11_backup/teddy-subtitle-normal.timer" ]]; then
  if [[ "$(cat "$stage11_backup/timer-enabled.txt")" == enabled ]]; then
    systemctl enable teddy-subtitle-normal.timer
  fi
  if [[ "$(cat "$stage11_backup/timer-active.txt")" == active ]]; then
    systemctl start teddy-subtitle-normal.timer
  fi
fi
echo 'NORMAL_MODE_ROLLBACK=COMPLETE; artifacts and queue history retained'
