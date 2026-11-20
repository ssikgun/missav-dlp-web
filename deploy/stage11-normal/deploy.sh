#!/bin/bash
set -euo pipefail
umask 077

stage11_origin='https://github.com/ssikgun/missav-dlp-web.git'
stage11_branch='teddy-subtitle-stage11'
stage11_deployment='/opt/missav-dlp-web/discovery/stage11-normal-deployment'
stage11_python='/opt/stage11-stt-venv/bin/python'
stage11_lock_dir='/opt/missav-dlp-web/title-locks'

stage11_action='deploy'
if [[ "${1:-}" == 'prepare' || "${1:-}" == 'switch-current' || "${1:-}" == 'activate-timer' ]]; then
  stage11_action="$1"
  stage11_revision="${2:?Usage: deploy.sh {prepare|switch-current|activate-timer} COMMIT_SHA}"
  [[ "$#" -eq 2 ]]
else
  stage11_revision="${1:?Usage: deploy.sh COMMIT_SHA}"
  [[ "$#" -eq 1 ]]
fi
[[ "$stage11_revision" =~ ^[0-9a-f]{40}$ ]]

stage11_canonical_deployment="$(realpath -m -- "$stage11_deployment")"
[[ "$stage11_canonical_deployment" == "$stage11_deployment" ]] || {
  echo 'DEPLOY=BLOCKED_DEPLOYMENT_PATH_LINK' >&2; exit 1;
}
stage11_releases="$stage11_deployment/releases"
stage11_release="$stage11_releases/$stage11_revision"
stage11_prepare="$stage11_releases/.prepare-$stage11_revision"
stage11_preflight_dir="$stage11_deployment/preflight"
stage11_backup=''
stage11_preflight_log=''

verify_release() {
  local stage11_path="$1"
  [[ -d "$stage11_path" && ! -L "$stage11_path" ]] || {
    echo 'DEPLOY=BLOCKED_RELEASE_MISSING' >&2; return 1;
  }
  [[ "$(git -C "$stage11_path" rev-parse --show-toplevel)" == "$stage11_path" ]]
  [[ "$(git -C "$stage11_path" rev-parse HEAD)" == "$stage11_revision" ]]
  [[ "$(git -C "$stage11_path" branch --show-current)" == '' ]]
  [[ "$(git -C "$stage11_path" remote get-url origin)" == "$stage11_origin" ]]
  [[ -z "$(git -C "$stage11_path" status --porcelain=v1 --untracked-files=all)" ]] || {
    echo 'DEPLOY=BLOCKED_RELEASE_DIRTY' >&2; return 1;
  }
  git -C "$stage11_path" merge-base --is-ancestor \
    "$stage11_revision" "refs/remotes/origin/$stage11_branch"
}

run_preflight() {
  local stage11_path="$1"
  stage11_preflight_log="$stage11_revision-$(date +%Y%m%d-%H%M%S)-$$.log"
  local stage11_log="$stage11_preflight_dir/$stage11_preflight_log"
  mkdir -p -- "$stage11_preflight_dir"
  [[ ! -e "$stage11_log" && ! -L "$stage11_log" ]]
  TEDDY_TITLE_LOCK_DIR="$stage11_lock_dir" "$stage11_python" -u \
    "$stage11_path/teddy_discovery_stage12_bulk_runner.py" \
    --mode preflight --batch-size 1 --expected-head "$stage11_revision" \
    > "$stage11_log" 2>&1
}

record_prepared_release() {
  local stage11_marker="$stage11_preflight_dir/$stage11_revision.prepared"
  local stage11_expected="STAGE11_PREPARED_HEAD=$stage11_revision
STAGE11_PREPARED_ORIGIN=$stage11_origin"
  if [[ -e "$stage11_marker" || -L "$stage11_marker" ]]; then
    [[ -f "$stage11_marker" && ! -L "$stage11_marker" ]]
    [[ "$(sed -n '1,2p' "$stage11_marker")" == "$stage11_expected" ]]
    return
  fi
  local stage11_marker_next="$stage11_marker.next.$$"
  [[ ! -e "$stage11_marker_next" && ! -L "$stage11_marker_next" ]]
  printf '%s\nSTAGE11_PREFLIGHT_LOG=%s\n' \
    "$stage11_expected" "$stage11_preflight_log" > "$stage11_marker_next"
  mv -- "$stage11_marker_next" "$stage11_marker"
}

prepare_release() {
  mkdir -p -- "$stage11_releases"
  if [[ -e "$stage11_release" || -L "$stage11_release" ]]; then
    verify_release "$stage11_release"
    run_preflight "$stage11_release"
    record_prepared_release
    printf 'RELEASE_PREPARED=%s\n' "$stage11_revision"
    return
  fi

  if [[ -e "$stage11_prepare" || -L "$stage11_prepare" ]]; then
    verify_release "$stage11_prepare"
  else
    git clone --no-checkout --branch "$stage11_branch" --single-branch \
      "$stage11_origin" "$stage11_prepare"
    git -C "$stage11_prepare" fetch --no-tags origin "$stage11_revision"
    [[ "$(git -C "$stage11_prepare" remote get-url origin)" == "$stage11_origin" ]]
    git -C "$stage11_prepare" merge-base --is-ancestor \
      "$stage11_revision" "refs/remotes/origin/$stage11_branch"
    git -C "$stage11_prepare" checkout --detach "$stage11_revision"
    verify_release "$stage11_prepare"
  fi

  run_preflight "$stage11_prepare"
  [[ ! -e "$stage11_release" && ! -L "$stage11_release" ]] || {
    echo 'DEPLOY=BLOCKED_RELEASE_COLLISION' >&2; return 1;
  }
  mv -- "$stage11_prepare" "$stage11_release"
  verify_release "$stage11_release"
  record_prepared_release
  printf 'RELEASE_PREPARED=%s\n' "$stage11_revision"
  printf 'RELEASE_PATH=%s\n' "$stage11_release"
  printf 'TIMER=UNCHANGED\nCURRENT=UNCHANGED\n'
}

switch_current() {
  verify_release "$stage11_release"
  [[ -f "$stage11_preflight_dir/$stage11_revision.prepared" \
     && ! -L "$stage11_preflight_dir/$stage11_revision.prepared" ]]
  [[ "$(sed -n '1,2p' "$stage11_preflight_dir/$stage11_revision.prepared")" \
     == "STAGE11_PREPARED_HEAD=$stage11_revision
STAGE11_PREPARED_ORIGIN=$stage11_origin" ]]
  if systemctl is-active --quiet teddy-subtitle-normal.service; then
    echo 'DEPLOY=BLOCKED_ACTIVE_NORMAL_JOB' >&2
    return 1
  fi
  if systemctl is-active --quiet teddy-subtitle-normal.timer \
      || systemctl is-enabled --quiet teddy-subtitle-normal.timer; then
    echo 'DEPLOY=BLOCKED_TIMER_MUST_BE_DISABLED_BEFORE_SWITCH' >&2
    return 1
  fi

  stage11_backup="$stage11_deployment/backups/$(date +%Y%m%d-%H%M%S)-$stage11_revision"
  [[ ! -e "$stage11_backup" && ! -L "$stage11_backup" ]] || {
    echo 'DEPLOY=BLOCKED_BACKUP_COLLISION' >&2; return 1;
  }
  mkdir -p -- "$stage11_backup"
  systemctl is-enabled teddy-subtitle-normal.timer \
    > "$stage11_backup/timer-enabled.txt" 2>/dev/null || true
  systemctl is-active teddy-subtitle-normal.timer \
    > "$stage11_backup/timer-active.txt" 2>/dev/null || true
  for stage11_file in runtime.env current; do
    if [[ -e "$stage11_deployment/$stage11_file" || -L "$stage11_deployment/$stage11_file" ]]; then
      cp -a -- "$stage11_deployment/$stage11_file" "$stage11_backup/"
    fi
  done
  for stage11_unit in teddy-subtitle-normal.service teddy-subtitle-normal.timer; do
    if [[ -f "/etc/systemd/system/$stage11_unit" ]]; then
      cp -a -- "/etc/systemd/system/$stage11_unit" "$stage11_backup/"
    fi
  done

  [[ ! -e "$stage11_deployment/current.next" && ! -L "$stage11_deployment/current.next" ]]
  ln -s -- "$stage11_release" "$stage11_deployment/current.next"
  mv -Tf -- "$stage11_deployment/current.next" "$stage11_deployment/current"
  [[ ! -e "$stage11_deployment/runtime.env.next" && ! -L "$stage11_deployment/runtime.env.next" ]]
  printf 'STAGE11_NORMAL_HEAD=%s\n' "$stage11_revision" \
    > "$stage11_deployment/runtime.env.next"
  mv -f -- "$stage11_deployment/runtime.env.next" "$stage11_deployment/runtime.env"
  install -m 644 "$stage11_release/deploy/stage11-normal/teddy-subtitle-normal.service" /etc/systemd/system/
  install -m 644 "$stage11_release/deploy/stage11-normal/teddy-subtitle-normal.timer" /etc/systemd/system/
  systemctl daemon-reload
  printf 'CURRENT_SWITCHED=%s\nROLLBACK_BACKUP=%s\n' "$stage11_revision" "$stage11_backup"
  printf 'TIMER=UNCHANGED_DISABLED\n'
}

activate_timer() {
  verify_release "$stage11_release"
  [[ -L "$stage11_deployment/current" ]]
  [[ "$(realpath -- "$stage11_deployment/current")" == "$stage11_release" ]]
  [[ -f "$stage11_deployment/runtime.env" && ! -L "$stage11_deployment/runtime.env" ]]
  [[ "$(cat -- "$stage11_deployment/runtime.env")" == "STAGE11_NORMAL_HEAD=$stage11_revision" ]]
  if systemctl is-active --quiet teddy-subtitle-normal.service; then
    echo 'DEPLOY=BLOCKED_ACTIVE_NORMAL_JOB' >&2
    return 1
  fi
  systemctl enable --now teddy-subtitle-normal.timer
  printf 'TIMER_ACTIVATED=%s\n' "$stage11_revision"
  systemctl show teddy-subtitle-normal.timer -p ActiveState -p SubState -p NextElapseUSecMonotonic
}

case "$stage11_action" in
  prepare)
    prepare_release
    ;;
  switch-current)
    switch_current
    ;;
  activate-timer)
    activate_timer
    ;;
  deploy)
    prepare_release
    switch_current
    activate_timer
    ;;
esac
