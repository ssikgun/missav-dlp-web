#!/bin/bash
set -euo pipefail
umask 077
stage11_source="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
stage11_revision="${1:?Usage: deploy.sh COMMIT_SHA}"
[[ "$stage11_revision" =~ ^[0-9a-f]{40}$ ]]
[[ "$(git -C "$stage11_source" rev-parse "$stage11_revision")" == "$stage11_revision" ]]
stage11_deployment=/opt/missav-dlp-web/discovery/stage11-normal-deployment
stage11_release="$stage11_deployment/releases/$stage11_revision"
stage11_backup="$stage11_deployment/backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$stage11_deployment/releases" "$stage11_backup"
systemctl is-enabled teddy-subtitle-normal.timer > "$stage11_backup/timer-enabled.txt" 2>/dev/null || true
systemctl is-active teddy-subtitle-normal.timer > "$stage11_backup/timer-active.txt" 2>/dev/null || true
# Only this subtitle unit is touched; existing web, completion and GPU services stay live.
if systemctl is-active --quiet teddy-subtitle-normal.service; then
  echo 'DEPLOY=BLOCKED_ACTIVE_NORMAL_JOB' >&2
  exit 1
fi
for stage11_file in runtime.env current; do
  if [[ -e "$stage11_deployment/$stage11_file" || -L "$stage11_deployment/$stage11_file" ]]; then
    cp -a "$stage11_deployment/$stage11_file" "$stage11_backup/"
  fi
done
for stage11_unit in teddy-subtitle-normal.service teddy-subtitle-normal.timer; do
  if [[ -f "/etc/systemd/system/$stage11_unit" ]]; then
    cp -a "/etc/systemd/system/$stage11_unit" "$stage11_backup/"
  fi
done
if [[ ! -d "$stage11_release" ]]; then
  git -C "$stage11_source" worktree add --detach "$stage11_release" "$stage11_revision"
fi
[[ -z "$(git -C "$stage11_release" status --porcelain)" ]]
TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks /opt/stage11-stt-venv/bin/python -u "$stage11_release/teddy_discovery_stage12_bulk_runner.py" \
  --mode preflight --batch-size 1 --expected-head "$stage11_revision" > "$stage11_backup/preflight.log" 2>&1
ln -s "$stage11_release" "$stage11_deployment/current.next"
mv -Tf "$stage11_deployment/current.next" "$stage11_deployment/current"
printf 'STAGE11_NORMAL_HEAD=%s\n' "$stage11_revision" > "$stage11_deployment/runtime.env"
install -m 644 "$stage11_release/deploy/stage11-normal/teddy-subtitle-normal.service" /etc/systemd/system/
install -m 644 "$stage11_release/deploy/stage11-normal/teddy-subtitle-normal.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now teddy-subtitle-normal.timer
printf 'DEPLOYED_HEAD=%s\nROLLBACK_BACKUP=%s\n' "$stage11_revision" "$stage11_backup"
systemctl show teddy-subtitle-normal.timer -p ActiveState -p SubState -p NextElapseUSecMonotonic
