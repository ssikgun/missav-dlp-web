#!/bin/bash
set -euo pipefail
umask 077
stage11_backup="${1:?Usage: rollback.sh BACKUP_DIRECTORY}"
stage11_deployment=/opt/missav-dlp-web/discovery/stage11-normal-deployment
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
for stage11_file in current runtime.env; do
  if [[ -e "$stage11_backup/$stage11_file" || -L "$stage11_backup/$stage11_file" ]]; then
    cp -a --remove-destination "$stage11_backup/$stage11_file" "$stage11_deployment/$stage11_file"
  else
    rm -f "$stage11_deployment/$stage11_file"
  fi
done
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
