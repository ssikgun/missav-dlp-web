#!/usr/bin/env bash

# Shared fail-closed helpers for the explicit paused deploy/rollback paths.
# The caller sets stage11_deployment and stage11_systemd_dir before sourcing.

stage11_require_paused_state() {
  local timer_enabled timer_active service_active
  timer_enabled="$(systemctl is-enabled teddy-subtitle-normal.timer 2>/dev/null || true)"
  timer_active="$(systemctl is-active teddy-subtitle-normal.timer 2>/dev/null || true)"
  service_active="$(systemctl is-active teddy-subtitle-normal.service 2>/dev/null || true)"
  if [[ "$timer_enabled" == disabled \
      && "$timer_active" == inactive \
      && "$service_active" == inactive ]]; then
    return 0
  fi
  printf 'PAUSED_STATE=BLOCKED timer_enabled=%s timer_active=%s service_active=%s\n' \
    "$timer_enabled" "$timer_active" "$service_active" >&2
  return 1
}

stage11_disable_paused_timer() {
  systemctl disable --now teddy-subtitle-normal.timer || {
    echo 'PAUSED_TIMER=DISABLE_FAILED' >&2
    return 1
  }
  local timer_enabled timer_active
  timer_enabled="$(systemctl is-enabled teddy-subtitle-normal.timer 2>/dev/null || true)"
  timer_active="$(systemctl is-active teddy-subtitle-normal.timer 2>/dev/null || true)"
  if [[ "$timer_enabled" != disabled || "$timer_active" != inactive ]]; then
    printf 'PAUSED_TIMER=NOT_QUIESCENT enabled=%s active=%s\n' \
      "$timer_enabled" "$timer_active" >&2
    return 1
  fi
}

stage11_write_paused_backup_manifest() {
  local backup="$1"
  (
    cd -- "$backup"
    sha256sum \
      mode.txt timer-enabled.txt timer-active.txt \
      current-target.txt current-head.txt runtime.env \
      service-unit-present.txt timer-unit-present.txt \
      teddy-subtitle-normal.service teddy-subtitle-normal.timer \
      > backup-manifest.sha256
  )
}

stage11_paused_backup_manifest_matches() {
  local backup="$1"
  cmp -s -- "$backup/backup-manifest.sha256" <(
    cd -- "$backup" && sha256sum \
      mode.txt timer-enabled.txt timer-active.txt \
      current-target.txt current-head.txt runtime.env \
      service-unit-present.txt timer-unit-present.txt \
      teddy-subtitle-normal.service teddy-subtitle-normal.timer
  )
}

stage11_capture_paused_backup() {
  local backup="$1" target head unit
  stage11_require_paused_state || return 1
  [[ -L "$stage11_deployment/current" \
      && -f "$stage11_deployment/runtime.env" ]] || {
    echo 'PAUSED_BACKUP=DEPLOYMENT_POINTER_OR_RUNTIME_MISSING' >&2
    return 1
  }
  target="$(readlink -- "$stage11_deployment/current")" || return 1
  head="$(git -C "$stage11_deployment/current" rev-parse HEAD 2>/dev/null || true)"
  [[ "$head" =~ ^[0-9a-f]{40}$ \
      && "$target" == "$stage11_deployment/releases/$head" \
      && -d "$target" \
      && "$(cat -- "$stage11_deployment/runtime.env")" == "STAGE11_NORMAL_HEAD=$head" ]] || {
    echo 'PAUSED_BACKUP=CURRENT_OR_RUNTIME_IDENTITY_INVALID' >&2
    return 1
  }
  for unit in teddy-subtitle-normal.service teddy-subtitle-normal.timer; do
    [[ -f "$stage11_systemd_dir/$unit" ]] || {
      printf 'PAUSED_BACKUP=UNIT_MISSING_%s\n' "$unit" >&2
      return 1
    }
  done

  mkdir -p -- "$backup" || return 1
  printf 'paused\n' > "$backup/mode.txt" || return 1
  printf 'disabled\n' > "$backup/timer-enabled.txt" || return 1
  printf 'inactive\n' > "$backup/timer-active.txt" || return 1
  printf '%s\n' "$target" > "$backup/current-target.txt" || return 1
  printf '%s\n' "$head" > "$backup/current-head.txt" || return 1
  printf 'yes\n' > "$backup/service-unit-present.txt" || return 1
  printf 'yes\n' > "$backup/timer-unit-present.txt" || return 1
  cp -a -- "$stage11_deployment/current" "$backup/current" || return 1
  cp -a -- "$stage11_deployment/runtime.env" "$backup/runtime.env" || return 1
  cp -a -- "$stage11_systemd_dir/teddy-subtitle-normal.service" "$backup/" || return 1
  cp -a -- "$stage11_systemd_dir/teddy-subtitle-normal.timer" "$backup/" || return 1
  stage11_write_paused_backup_manifest "$backup" || return 1
  stage11_validate_paused_backup "$backup"
}

stage11_validate_paused_backup() {
  local backup="$1" target head
  [[ -d "$backup" && ! -L "$backup" ]] || {
    echo 'PAUSED_BACKUP=INVALID_DIRECTORY' >&2
    return 1
  }
  local required
  for required in \
    mode.txt timer-enabled.txt timer-active.txt current current-target.txt \
    current-head.txt runtime.env service-unit-present.txt timer-unit-present.txt \
    teddy-subtitle-normal.service teddy-subtitle-normal.timer backup-manifest.sha256; do
    [[ -e "$backup/$required" || -L "$backup/$required" ]] || {
      printf 'PAUSED_BACKUP=MISSING_%s\n' "$required" >&2
      return 1
    }
  done
  for required in mode.txt timer-enabled.txt timer-active.txt current-target.txt \
    current-head.txt runtime.env service-unit-present.txt timer-unit-present.txt \
    teddy-subtitle-normal.service teddy-subtitle-normal.timer backup-manifest.sha256; do
    [[ -f "$backup/$required" && ! -L "$backup/$required" ]] || {
      printf 'PAUSED_BACKUP=INVALID_%s\n' "$required" >&2
      return 1
    }
  done
  [[ "$(cat -- "$backup/mode.txt")" == paused \
      && "$(cat -- "$backup/timer-enabled.txt")" == disabled \
      && "$(cat -- "$backup/timer-active.txt")" == inactive \
      && "$(cat -- "$backup/service-unit-present.txt")" == yes \
      && "$(cat -- "$backup/timer-unit-present.txt")" == yes ]] || {
    echo 'PAUSED_BACKUP=STATE_OR_MODE_MISMATCH' >&2
    return 1
  }
  [[ -L "$backup/current" ]] || {
    echo 'PAUSED_BACKUP=CURRENT_NOT_SYMLINK' >&2
    return 1
  }
  target="$(cat -- "$backup/current-target.txt")"
  head="$(cat -- "$backup/current-head.txt")"
  [[ "$head" =~ ^[0-9a-f]{40}$ \
      && "$target" == "$stage11_deployment/releases/$head" \
      && "$(readlink -- "$backup/current")" == "$target" \
      && -d "$target" ]] || {
    echo 'PAUSED_BACKUP=CURRENT_IDENTITY_INVALID' >&2
    return 1
  }
  [[ "$(git -C "$backup/current" rev-parse HEAD 2>/dev/null || true)" == "$head" \
      && "$(cat -- "$backup/runtime.env")" == "STAGE11_NORMAL_HEAD=$head" ]] || {
    echo 'PAUSED_BACKUP=RELEASE_OR_RUNTIME_IDENTITY_INVALID' >&2
    return 1
  }
  stage11_paused_backup_manifest_matches "$backup" || {
    echo 'PAUSED_BACKUP=CHECKSUM_MISMATCH' >&2
    return 1
  }
}

stage11_restore_paused_backup() {
  local backup="$1" unit target head temp
  stage11_disable_paused_timer || return 1
  stage11_require_paused_state || return 1
  stage11_validate_paused_backup "$backup" || return 1

  for unit in teddy-subtitle-normal.service teddy-subtitle-normal.timer; do
    temp="$stage11_systemd_dir/.${unit}.restore.$$"
    [[ ! -e "$temp" && ! -L "$temp" ]] || {
      printf 'PAUSED_ROLLBACK=RESTORE_TEMP_EXISTS_%s\n' "$unit" >&2
      return 1
    }
    cp -a -- "$backup/$unit" "$temp" || return 1
    mv -f -- "$temp" "$stage11_systemd_dir/$unit" || return 1
  done

  temp="$stage11_deployment/.runtime.env.restore.$$"
  [[ ! -e "$temp" && ! -L "$temp" ]] || return 1
  cp -a -- "$backup/runtime.env" "$temp" || return 1
  mv -f -- "$temp" "$stage11_deployment/runtime.env" || return 1

  temp="$stage11_deployment/current.restore.$$"
  [[ ! -e "$temp" && ! -L "$temp" ]] || return 1
  cp -a -- "$backup/current" "$temp" || return 1
  mv -Tf -- "$temp" "$stage11_deployment/current" || return 1

  systemctl daemon-reload || return 1
  stage11_require_paused_state || return 1
  stage11_validate_paused_backup "$backup" || return 1

  target="$(cat -- "$backup/current-target.txt")"
  head="$(cat -- "$backup/current-head.txt")"
  [[ "$(readlink -- "$stage11_deployment/current")" == "$target" \
      && "$(git -C "$stage11_deployment/current" rev-parse HEAD 2>/dev/null || true)" == "$head" \
      && "$(cat -- "$stage11_deployment/runtime.env")" == "STAGE11_NORMAL_HEAD=$head" ]] || {
    echo 'PAUSED_ROLLBACK=RESTORED_IDENTITY_MISMATCH' >&2
    return 1
  }
  cmp -s -- "$backup/teddy-subtitle-normal.service" \
    "$stage11_systemd_dir/teddy-subtitle-normal.service" || return 1
  cmp -s -- "$backup/teddy-subtitle-normal.timer" \
    "$stage11_systemd_dir/teddy-subtitle-normal.timer" || return 1
}
