#!/bin/bash
set -euo pipefail
umask 077
stage11_script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
stage11_source="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
source "$stage11_script_dir/paused-common.sh"
stage11_mode=normal
if [[ "${1:-}" == --paused ]]; then
  stage11_mode=paused
  shift
fi
if [[ "$#" -ne 1 ]]; then
  echo 'Usage: deploy.sh [--paused] COMMIT_SHA' >&2
  exit 2
fi
stage11_revision="$1"
[[ "$stage11_revision" =~ ^[0-9a-f]{40}$ ]]
[[ "$(git -C "$stage11_source" rev-parse "$stage11_revision")" == "$stage11_revision" ]]
stage11_deployment=/opt/missav-dlp-web/discovery/stage11-normal-deployment
stage11_systemd_dir=/etc/systemd/system
stage11_release="$stage11_deployment/releases/$stage11_revision"
stage11_backup=''
stage11_operational_mutation=0
stage11_runtime_next="$stage11_deployment/.runtime.env.next.$$"

stage11_paused_deploy_exit() {
  local exit_status=$?
  trap - EXIT
  if [[ "$stage11_mode" == paused && "$exit_status" -ne 0 ]]; then
    if [[ -L "$stage11_deployment/current.next" \
        && "$(readlink -- "$stage11_deployment/current.next")" == "$stage11_release" ]]; then
      rm -f -- "$stage11_deployment/current.next"
    fi
    rm -f -- "$stage11_runtime_next"
    if (( stage11_operational_mutation == 1 )); then
      echo 'DEPLOY=PAUSED_FAILURE_RESTORING' >&2
      if stage11_restore_paused_backup "$stage11_backup"; then
        echo 'DEPLOY=PAUSED_FAILURE_ROLLED_BACK' >&2
      else
        echo 'DEPLOY=PAUSED_FAILURE_ROLLBACK_INCOMPLETE; timer was not started' >&2
      fi
    elif [[ -n "$stage11_backup" ]]; then
      local timer_enabled timer_active
      timer_enabled="$(systemctl is-enabled teddy-subtitle-normal.timer 2>/dev/null || true)"
      timer_active="$(systemctl is-active teddy-subtitle-normal.timer 2>/dev/null || true)"
      if [[ "$timer_enabled" != disabled || "$timer_active" != inactive ]]; then
        stage11_disable_paused_timer || true
      fi
    fi
  fi
  exit "$exit_status"
}

if [[ "$stage11_mode" == paused ]]; then
  stage11_require_paused_state
  mkdir -p -- "$stage11_deployment/releases" "$stage11_deployment/backups"
  stage11_backup="$(mktemp -d "$stage11_deployment/backups/$(date +%Y%m%d-%H%M%S)-XXXXXXXX")"
  trap stage11_paused_deploy_exit EXIT
  stage11_capture_paused_backup "$stage11_backup"
else
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
    if [[ -f "$stage11_systemd_dir/$stage11_unit" ]]; then
      cp -a "$stage11_systemd_dir/$stage11_unit" "$stage11_backup/"
    fi
  done
fi

if [[ ! -d "$stage11_release" ]]; then
  git -C "$stage11_source" worktree add --detach "$stage11_release" "$stage11_revision"
fi
[[ -d "$stage11_release" && ! -L "$stage11_release" ]]
[[ "$(git -C "$stage11_release" rev-parse HEAD)" == "$stage11_revision" ]]
[[ -z "$(git -C "$stage11_release" status --porcelain)" ]]
if [[ "$stage11_mode" == paused ]]; then
  stage11_require_paused_state
fi
stage11_preflight_status=0
if TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks /opt/stage11-stt-venv/bin/python -u "$stage11_release/teddy_discovery_stage12_bulk_runner.py" \
  --mode preflight --batch-size 1 --expected-head "$stage11_revision" > "$stage11_backup/preflight.log" 2>&1; then
  stage11_preflight_status=0
else
  stage11_preflight_status=$?
fi
if [[ "$stage11_mode" == paused ]]; then
  stage11_require_paused_state
fi
if [[ "$stage11_preflight_status" -ne 0 ]]; then
  printf 'DEPLOY=PREFLIGHT_FAILED status=%s log=%s\n' \
    "$stage11_preflight_status" "$stage11_backup/preflight.log" >&2
  exit "$stage11_preflight_status"
fi

if [[ "$stage11_mode" == paused ]]; then
  stage11_require_paused_state
else
  ln -s "$stage11_release" "$stage11_deployment/current.next"
fi
if [[ "$stage11_mode" == paused ]]; then
  [[ ! -e "$stage11_deployment/current.next" \
      && ! -L "$stage11_deployment/current.next" ]]
  [[ ! -e "$stage11_runtime_next" && ! -L "$stage11_runtime_next" ]]
  ln -s "$stage11_release" "$stage11_deployment/current.next"
  stage11_require_paused_state
  stage11_operational_mutation=1
fi
mv -Tf "$stage11_deployment/current.next" "$stage11_deployment/current"
if [[ "$stage11_mode" == paused ]]; then
  stage11_require_paused_state
  printf 'STAGE11_NORMAL_HEAD=%s\n' "$stage11_revision" > "$stage11_runtime_next"
  mv -f "$stage11_runtime_next" "$stage11_deployment/runtime.env"
  stage11_require_paused_state
else
  printf 'STAGE11_NORMAL_HEAD=%s\n' "$stage11_revision" > "$stage11_deployment/runtime.env"
fi
install -m 644 "$stage11_release/deploy/stage11-normal/teddy-subtitle-normal.service" "$stage11_systemd_dir/"
if [[ "$stage11_mode" == paused ]]; then
  stage11_require_paused_state
fi
install -m 644 "$stage11_release/deploy/stage11-normal/teddy-subtitle-normal.timer" "$stage11_systemd_dir/"
if [[ "$stage11_mode" == paused ]]; then
  stage11_require_paused_state
fi
systemctl daemon-reload
if [[ "$stage11_mode" == paused ]]; then
  stage11_require_paused_state
else
  systemctl enable --now teddy-subtitle-normal.timer
fi
printf 'DEPLOYED_HEAD=%s\nROLLBACK_BACKUP=%s\n' "$stage11_revision" "$stage11_backup"
if [[ "$stage11_mode" == paused ]]; then
  echo 'DEPLOY_MODE=PAUSED_TIMER_REMAINS_DISABLED'
else
  systemctl show teddy-subtitle-normal.timer -p ActiveState -p SubState -p NextElapseUSecMonotonic
fi
