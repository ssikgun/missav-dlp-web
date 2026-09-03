#!/usr/bin/env bash
set -u
set -o pipefail


EXPECTED_HEAD="66b13b6bbf9e930e73e7fdff9960581ab7b30a88"

PRODUCTION_ROOT=${TEDDY_STAGE10_B4_PRODUCTION_ROOT:-/opt/missav-dlp-web}
RUNTIME_DIR="$PRODUCTION_ROOT/stage9-runtime"
DISCOVERY_DB="$PRODUCTION_ROOT/discovery/teddy-discovery.sqlite3"
SYSTEMD_ROOT=${TEDDY_STAGE10_B4_SYSTEMD_ROOT:-/etc/systemd/system}
SYSTEM_BIN_ROOT=${TEDDY_STAGE10_B4_SYSTEM_BIN_ROOT:-/usr/local/sbin}

ENV_FILE="/etc/default/teddy-discovery"
STAGE9_MARKER="$RUNTIME_DIR/.teddy-stage9-commit"
STAGE10_B3_MARKER="$RUNTIME_DIR/.teddy-stage10-b3-commit"
STAGE10_B4_MARKER="$RUNTIME_DIR/.teddy-stage10-b4-commit"

STAGE9_WRAPPER="$SYSTEM_BIN_ROOT/teddy-completion-stage9-runner"
STAGE9_SERVICE="$SYSTEMD_ROOT/teddy-completion-stage9.service"
STAGE9_TIMER="$SYSTEMD_ROOT/teddy-completion-stage9.timer"
STAGE9_SERVICE_NAME="teddy-completion-stage9.service"
STAGE9_TIMER_NAME="teddy-completion-stage9.timer"

REPORT_WRAPPER="$SYSTEM_BIN_ROOT/teddy-discovery-jav-reconcile-report"
REPORT_SERVICE="$SYSTEMD_ROOT/teddy-discovery-jav-reconcile.service"
REPORT_TIMER="$SYSTEMD_ROOT/teddy-discovery-jav-reconcile.timer"
REPORT_SERVICE_NAME="teddy-discovery-jav-reconcile.service"
REPORT_TIMER_NAME="teddy-discovery-jav-reconcile.timer"

APPLY_WRAPPER="$SYSTEM_BIN_ROOT/teddy-discovery-jav-reconcile-apply"
APPLY_SERVICE="$SYSTEMD_ROOT/teddy-discovery-jav-reconcile-apply.service"
APPLY_TIMER="$SYSTEMD_ROOT/teddy-discovery-jav-reconcile-apply.timer"
APPLY_SERVICE_DROPIN="$SYSTEMD_ROOT/teddy-discovery-jav-reconcile-apply.service.d"
APPLY_SERVICE_NAME="teddy-discovery-jav-reconcile-apply.service"

RUNTIME_UPDATE_FILES=(
    "teddy_discovery_jav_reconcile.py"
    "teddy_discovery_organizer_apply.py"
)

BACKUP_DIR="${1:-}"
FAILURE_POINT="UNKNOWN"
STAGE9_TIMER_ENABLED_BEFORE="UNKNOWN"
STAGE9_TIMER_ACTIVE_BEFORE="UNKNOWN"
REPORT_TIMER_ENABLED_BEFORE="UNKNOWN"
REPORT_TIMER_ACTIVE_BEFORE="UNKNOWN"
STAGE9_TIMER_ACTIVE_AFTER="UNKNOWN"
REPORT_TIMER_ACTIVE_AFTER="UNKNOWN"
STAGE9_TIMER_STOP_ATTEMPTED=0
REPORT_TIMER_STOP_ATTEMPTED=0
STAGE9_TIMER_RESTORED=0
REPORT_TIMER_RESTORED=0
CLEANUP_DONE=0
CLEANUP_STATUS="NOT_REQUIRED"
CLEANUP_OUTPUT=1


failure_report()
{
    printf '%s\n' "RESULT=FAIL"
    printf '%s\n' "FAILURE_POINT=${FAILURE_POINT:-UNKNOWN}"
    printf '%s\n' "BACKUP_DIR=${BACKUP_DIR:-UNAVAILABLE}"
    printf '%s\n' "APPLY_TIMER=ABSENT_EXPECTED"
    printf '%s\n' "TIMER_CLEANUP=$CLEANUP_STATUS"
    printf '%s\n' "AUTO_APPLY_ENABLED=NO"
}


success_report()
{
    local stage9_enabled_after report_enabled_after

    stage9_enabled_after=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    report_enabled_after=$(unit_state is-enabled "$REPORT_TIMER_NAME")
    printf '%s\n' "RESULT=PASS"
    printf '%s\n' "BACKUP_DIR=$BACKUP_DIR"
    printf '%s\n' "APPLY_SERVICE=REMOVED"
    printf '%s\n' "APPLY_TIMER=ABSENT"
    printf '%s\n' "STAGE9_TIMER_ENABLED_BEFORE=$STAGE9_TIMER_ENABLED_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ENABLED_AFTER=$stage9_enabled_after"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_BEFORE=$STAGE9_TIMER_ACTIVE_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_AFTER=$STAGE9_TIMER_ACTIVE_AFTER"
    printf '%s\n' "REPORT_TIMER_ENABLED_BEFORE=$REPORT_TIMER_ENABLED_BEFORE"
    printf '%s\n' "REPORT_TIMER_ENABLED_AFTER=$report_enabled_after"
    printf '%s\n' "REPORT_TIMER_ACTIVE_BEFORE=$REPORT_TIMER_ACTIVE_BEFORE"
    printf '%s\n' "REPORT_TIMER_ACTIVE_AFTER=$REPORT_TIMER_ACTIVE_AFTER"
    printf '%s\n' "ENV_FILE=UNCHANGED"
    printf '%s\n' "AUTO_APPLY_ENABLED=NO"
}


fail_at()
{
    FAILURE_POINT=$1
    return 1
}


require_command()
{
    command -v "$1" >/dev/null 2>&1 || {
        fail_at "MISSING_COMMAND_$1"
        return 1
    }
}


require_regular()
{
    local path=$1
    local reason=$2
    if [ ! -f "$path" ] || [ -L "$path" ]; then
        fail_at "$reason"
        return 1
    fi
    return 0
}


require_absent()
{
    local path=$1
    local reason=$2
    if [ -e "$path" ] || [ -L "$path" ]; then
        fail_at "$reason"
        return 1
    fi
    return 0
}


verify_metadata()
{
    local path=$1
    local mode=$2
    local expected_mode=${mode#0}
    [ "$(stat -c '%u:%g %a' "$path" 2>/dev/null)" = "0:0 $expected_mode" ]
}


sha256_file()
{
    sha256sum "$1" | awk '{print $1}'
}


unit_state()
{
    systemctl "$1" "$2" 2>/dev/null
}


valid_enabled_state()
{
    case "$1" in
        enabled|enabled-runtime|disabled|static|indirect|masked|generated|transient|not-found)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}


valid_active_state()
{
    case "$1" in
        active|inactive|failed|activating|deactivating|unknown)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}


state_value()
{
    awk -F= -v wanted="$1" '$1 == wanted { value = $2 } END { print value }' "$BACKUP_DIR/pre-state.txt"
}


atomic_restore()
{
    local source_path=$1
    local target_path=$2
    local mode=$3
    local temp_path="${target_path}.stage10-b4-rollback.$$"
    local source_hash temp_hash

    require_regular "$source_path" "BACKUP_RESTORE_SOURCE_INVALID" || return 1
    rm -f -- "$temp_path"
    install -o root -g root -m "$mode" -- "$source_path" "$temp_path" || {
        rm -f -- "$temp_path"
        return 1
    }
    source_hash=$(sha256_file "$source_path") || { rm -f -- "$temp_path"; return 1; }
    temp_hash=$(sha256_file "$temp_path") || { rm -f -- "$temp_path"; return 1; }
    if [ "$source_hash" != "$temp_hash" ]; then
        rm -f -- "$temp_path"
        return 1
    fi
    mv -f -- "$temp_path" "$target_path" || {
        rm -f -- "$temp_path"
        return 1
    }
    return 0
}


wait_service_quiesced()
{
    local service_name=$1
    local label=$2
    local elapsed=0
    local state

    while :; do
        state=$(unit_state is-active "$service_name")
        case "$state" in
            inactive|failed)
                return 0
                ;;
            active|activating|deactivating)
                if [ "$elapsed" -ge 120 ]; then
                    fail_at "${label}_SERVICE_DID_NOT_QUIESCE"
                    return 1
                fi
                sleep 1
                elapsed=$((elapsed + 1))
                ;;
            *)
                fail_at "${label}_SERVICE_STATE_UNREADABLE_DURING_QUIESCE"
                return 1
                ;;
        esac
    done
}


restore_active_timers()
{
    local rc=0
    local timers_ok=1

    if [ "$STAGE9_TIMER_ACTIVE_BEFORE" = "active" ] && \
        [ "$STAGE9_TIMER_STOP_ATTEMPTED" -eq 1 ] && \
        [ "$STAGE9_TIMER_RESTORED" -eq 0 ]; then
        if systemctl start "$STAGE9_TIMER_NAME" >/dev/null 2>&1 && \
            [ "$(unit_state is-active "$STAGE9_TIMER_NAME")" = "active" ]; then
            STAGE9_TIMER_RESTORED=1
            STAGE9_TIMER_ACTIVE_AFTER=active
        else
            rc=1
            STAGE9_TIMER_ACTIVE_AFTER=$(unit_state is-active "$STAGE9_TIMER_NAME")
        fi
    fi
    if [ "$REPORT_TIMER_ACTIVE_BEFORE" = "active" ] && \
        [ "$REPORT_TIMER_STOP_ATTEMPTED" -eq 1 ] && \
        [ "$REPORT_TIMER_RESTORED" -eq 0 ]; then
        if systemctl start "$REPORT_TIMER_NAME" >/dev/null 2>&1 && \
            [ "$(unit_state is-active "$REPORT_TIMER_NAME")" = "active" ]; then
            REPORT_TIMER_RESTORED=1
            REPORT_TIMER_ACTIVE_AFTER=active
        else
            rc=1
            REPORT_TIMER_ACTIVE_AFTER=$(unit_state is-active "$REPORT_TIMER_NAME")
        fi
    fi
    if [ "$STAGE9_TIMER_ACTIVE_BEFORE" = "active" ] && \
        [ "$STAGE9_TIMER_RESTORED" -ne 1 ]; then
        timers_ok=0
    fi
    if [ "$REPORT_TIMER_ACTIVE_BEFORE" = "active" ] && \
        [ "$REPORT_TIMER_RESTORED" -ne 1 ]; then
        timers_ok=0
    fi
    if [ "$rc" -eq 0 ] && [ "$timers_ok" -eq 1 ]; then
        CLEANUP_STATUS="PASS"
    else
        CLEANUP_STATUS="FAIL"
    fi
    return "$rc"
}


cleanup_timers()
{
    local rc
    if [ "$CLEANUP_DONE" -eq 1 ]; then
        return 0
    fi
    CLEANUP_DONE=1
    restore_active_timers
    rc=$?
    STAGE9_TIMER_ACTIVE_AFTER=$(unit_state is-active "$STAGE9_TIMER_NAME")
    REPORT_TIMER_ACTIVE_AFTER=$(unit_state is-active "$REPORT_TIMER_NAME")
    if [ "$CLEANUP_OUTPUT" -eq 1 ] && [ "$rc" -ne 0 ]; then
        printf '%s\n' "TIMER_CLEANUP=FAIL"
        printf '%s\n' "HIGH_PRIORITY=TIMER_STATE_RESTORE_FAILED"
    fi
    return "$rc"
}


verify_pre_state_targets()
{
    local expected actual path name
    for pair in \
        "$REPORT_WRAPPER:report_wrapper_sha256" \
        "$REPORT_SERVICE:report_service_sha256" \
        "$REPORT_TIMER:report_timer_sha256" \
        "$STAGE9_WRAPPER:stage9_wrapper_sha256" \
        "$STAGE9_SERVICE:stage9_service_sha256" \
        "$STAGE9_TIMER:stage9_timer_sha256"; do
        path=${pair%%:*}
        name=${pair##*:}
        require_regular "$path" "REQUIRED_ARTIFACT_MISSING_$path" || return 1
        expected=$(state_value "$name")
        actual=$(sha256_file "$path") || return 1
        [ -n "$expected" ] && [ "$expected" = "$actual" ] || {
            fail_at "EXISTING_ARTIFACT_CHANGED_$path"
            return 1
        }
    done

    local env_stat env_hash marker_hash
    env_stat=$(state_value environment_file_stat)
    env_hash=$(state_value environment_file_sha256)
    verify_metadata "$ENV_FILE" 0600 || { fail_at "ENVIRONMENT_FILE_METADATA_CHANGED"; return 1; }
    [ "$(stat -c '%u:%g:%a:%s' "$ENV_FILE")" = "$env_stat" ] || { fail_at "ENVIRONMENT_FILE_METADATA_CHANGED"; return 1; }
    [ "$(sha256_file "$ENV_FILE")" = "$env_hash" ] || { fail_at "ENVIRONMENT_FILE_CHANGED"; return 1; }

    marker_hash=$(state_value stage9_marker_sha256)
    [ "$(sha256_file "$STAGE9_MARKER")" = "$marker_hash" ] || { fail_at "STAGE9_MARKER_CHANGED"; return 1; }
    marker_hash=$(state_value stage10_b3_marker_sha256)
    [ "$(sha256_file "$STAGE10_B3_MARKER")" = "$marker_hash" ] || { fail_at "STAGE10_B3_MARKER_CHANGED"; return 1; }
    return 0
}


verify_current_b4()
{
    local source_hash file
    require_regular "$STAGE10_B4_MARKER" "B4_MARKER_MISSING" || return 1
    verify_metadata "$STAGE10_B4_MARKER" 0644 || { fail_at "B4_MARKER_METADATA_INVALID"; return 1; }
    [ "$(cat "$STAGE10_B4_MARKER")" = "$EXPECTED_HEAD" ] || { fail_at "B4_MARKER_CONTENT_INVALID"; return 1; }
    [ "$(stat -c '%s' "$STAGE10_B4_MARKER")" = "41" ] || { fail_at "B4_MARKER_LENGTH_INVALID"; return 1; }
    require_regular "$RUNTIME_DIR/teddy_discovery_jav_reconcile_apply.py" "B4_RUNTIME_MISSING" || return 1
    require_regular "$APPLY_WRAPPER" "B4_WRAPPER_MISSING" || return 1
    require_regular "$APPLY_SERVICE" "B4_SERVICE_MISSING" || return 1
    verify_metadata "$RUNTIME_DIR/teddy_discovery_jav_reconcile_apply.py" 0644 || return 1
    verify_metadata "$APPLY_WRAPPER" 0755 || return 1
    verify_metadata "$APPLY_SERVICE" 0644 || return 1

    [ -f "$BACKUP_DIR/source-sha256.txt" ] || { fail_at "SOURCE_HASH_MANIFEST_MISSING"; return 1; }
    for file in "${RUNTIME_UPDATE_FILES[@]}" teddy_discovery_jav_reconcile_apply.py; do
        source_hash=$(awk -v wanted="$file" '$2 ~ ("/" wanted "$") { print $1 }' "$BACKUP_DIR/source-sha256.txt")
        [ -n "$source_hash" ] || { fail_at "B4_SOURCE_HASH_MISSING_$file"; return 1; }
        [ "$source_hash" = "$(sha256_file "$RUNTIME_DIR/$file")" ] || { fail_at "B4_RUNTIME_PROVENANCE_MISMATCH_$file"; return 1; }
    done
    source_hash=$(awk '$2 ~ /deploy\/systemd\/teddy-discovery-jav-reconcile-apply$/ { print $1 }' "$BACKUP_DIR/source-sha256.txt")
    [ "$source_hash" = "$(sha256_file "$APPLY_WRAPPER")" ] || { fail_at "B4_WRAPPER_PROVENANCE_MISMATCH"; return 1; }
    source_hash=$(awk '$2 ~ /deploy\/systemd\/teddy-discovery-jav-reconcile-apply.service$/ { print $1 }' "$BACKUP_DIR/source-sha256.txt")
    [ "$source_hash" = "$(sha256_file "$APPLY_SERVICE")" ] || { fail_at "B4_SERVICE_PROVENANCE_MISMATCH"; return 1; }
    return 0
}


stop_active_timer()
{
    local timer_name=$1
    local state=$2
    [ "$state" = "active" ] || return 0
    systemctl stop "$timer_name" >/dev/null 2>&1 || return 1
}


quiesce()
{
    local apply_state
    apply_state=$(unit_state is-active "$APPLY_SERVICE_NAME")
    case "$apply_state" in
        active|activating|deactivating)
            systemctl stop "$APPLY_SERVICE_NAME" >/dev/null 2>&1 || { fail_at "APPLY_SERVICE_STOP_FAILED"; return 1; }
            wait_service_quiesced "$APPLY_SERVICE_NAME" APPLY || return 1
            ;;
        inactive|failed)
            ;;
        *)
            fail_at "APPLY_SERVICE_STATE_UNREADABLE"
            return 1
            ;;
    esac

    local current_stage9_enabled current_report_enabled
    current_stage9_enabled=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    current_report_enabled=$(unit_state is-enabled "$REPORT_TIMER_NAME")
    [ "$current_stage9_enabled" = "$STAGE9_TIMER_ENABLED_BEFORE" ] || { fail_at "STAGE9_TIMER_ENABLED_CHANGED_EXTERNALLY"; return 1; }
    [ "$current_report_enabled" = "$REPORT_TIMER_ENABLED_BEFORE" ] || { fail_at "REPORT_TIMER_ENABLED_CHANGED_EXTERNALLY"; return 1; }

    local current_state
    current_state=$(unit_state is-active "$STAGE9_TIMER_NAME")
    valid_active_state "$current_state" || { fail_at "STAGE9_TIMER_ACTIVE_STATE_UNREADABLE"; return 1; }
    if [ "$STAGE9_TIMER_ACTIVE_BEFORE" = "active" ]; then
        STAGE9_TIMER_STOP_ATTEMPTED=1
    fi
    if [ "$current_state" = "active" ]; then
        STAGE9_TIMER_STOP_ATTEMPTED=1
        stop_active_timer "$STAGE9_TIMER_NAME" active || { fail_at "STAGE9_TIMER_STOP_FAILED"; return 1; }
    fi
    current_state=$(unit_state is-active "$REPORT_TIMER_NAME")
    valid_active_state "$current_state" || { fail_at "REPORT_TIMER_ACTIVE_STATE_UNREADABLE"; return 1; }
    if [ "$REPORT_TIMER_ACTIVE_BEFORE" = "active" ]; then
        REPORT_TIMER_STOP_ATTEMPTED=1
    fi
    if [ "$current_state" = "active" ]; then
        REPORT_TIMER_STOP_ATTEMPTED=1
        stop_active_timer "$REPORT_TIMER_NAME" active || { fail_at "REPORT_TIMER_STOP_FAILED"; return 1; }
    fi
    wait_service_quiesced "$STAGE9_SERVICE_NAME" STAGE9 || return 1
    wait_service_quiesced "$REPORT_SERVICE_NAME" REPORT || return 1
    return 0
}


restore_runtime()
{
    local file
    for file in "${RUNTIME_UPDATE_FILES[@]}"; do
        atomic_restore "$BACKUP_DIR/runtime/$file" "$RUNTIME_DIR/$file" 0644 || {
            fail_at "RUNTIME_RESTORE_FAILED_$file"
            return 1
        }
    done

    require_regular "$RUNTIME_DIR/teddy_discovery_jav_reconcile_apply.py" "B4_RUNTIME_CHANGED_DURING_QUIESCE" || return 1
    require_regular "$APPLY_WRAPPER" "B4_WRAPPER_CHANGED_DURING_QUIESCE" || return 1
    require_regular "$APPLY_SERVICE" "B4_SERVICE_CHANGED_DURING_QUIESCE" || return 1
    require_regular "$STAGE10_B4_MARKER" "B4_MARKER_CHANGED_DURING_QUIESCE" || return 1
    rm -f -- "$RUNTIME_DIR/teddy_discovery_jav_reconcile_apply.py"
    rm -f -- "$APPLY_WRAPPER" "$APPLY_SERVICE" "$STAGE10_B4_MARKER"
    if [ -e "$RUNTIME_DIR/teddy_discovery_jav_reconcile_apply.py" ] || \
        [ -L "$RUNTIME_DIR/teddy_discovery_jav_reconcile_apply.py" ] || \
        [ -e "$APPLY_WRAPPER" ] || [ -L "$APPLY_WRAPPER" ] || \
        [ -e "$APPLY_SERVICE" ] || [ -L "$APPLY_SERVICE" ] || \
        [ -e "$STAGE10_B4_MARKER" ] || [ -L "$STAGE10_B4_MARKER" ]; then
        fail_at "B4_ARTIFACT_REMOVE_FAILED"
        return 1
    fi
    return 0
}


restore_enabled_state()
{
    local unit=$1
    local wanted=$2
    local current

    current=$(unit_state is-enabled "$unit")
    [ "$current" = "$wanted" ] && return 0
    case "$wanted" in
        enabled)
            systemctl enable "$unit" >/dev/null 2>&1 || return 1
            ;;
        enabled-runtime)
            systemctl enable --runtime "$unit" >/dev/null 2>&1 || return 1
            ;;
        disabled)
            systemctl disable "$unit" >/dev/null 2>&1 || return 1
            ;;
        *)
            return 1
            ;;
    esac
    [ "$(unit_state is-enabled "$unit")" = "$wanted" ]
}


main()
{
    local file
    umask 077
    [ "$(id -u)" -eq 0 ] || { fail_at "ROOT_REQUIRED"; return 1; }
    for command_name in systemctl install mv rm awk id sleep stat cat sha256sum mkdir; do
        require_command "$command_name" || return 1
    done

    case "$BACKUP_DIR" in
        "$PRODUCTION_ROOT"/backups/stage10-b4-????????-??????)
            ;;
        *)
            fail_at "BACKUP_DIR_PATH_INVALID"
            return 1
            ;;
    esac
    [ -d "$BACKUP_DIR" ] || { fail_at "BACKUP_DIR_REQUIRED"; return 1; }
    [ -f "$BACKUP_DIR/pre-state.txt" ] || { fail_at "PRE_STATE_MISSING"; return 1; }
    [ -f "$BACKUP_DIR/source-sha256.txt" ] || { fail_at "SOURCE_HASH_MANIFEST_MISSING"; return 1; }
    [ "$(state_value source_head)" = "$EXPECTED_HEAD" ] || { fail_at "BACKUP_SOURCE_HEAD_MISMATCH"; return 1; }

    STAGE9_TIMER_ENABLED_BEFORE=$(state_value stage9_timer_enabled_before)
    STAGE9_TIMER_ACTIVE_BEFORE=$(state_value stage9_timer_active_before)
    REPORT_TIMER_ENABLED_BEFORE=$(state_value report_timer_enabled_before)
    REPORT_TIMER_ACTIVE_BEFORE=$(state_value report_timer_active_before)
    valid_enabled_state "$STAGE9_TIMER_ENABLED_BEFORE" || { fail_at "STAGE9_ENABLED_STATE_INVALID"; return 1; }
    valid_enabled_state "$REPORT_TIMER_ENABLED_BEFORE" || { fail_at "REPORT_ENABLED_STATE_INVALID"; return 1; }
    valid_active_state "$STAGE9_TIMER_ACTIVE_BEFORE" || { fail_at "STAGE9_ACTIVE_STATE_INVALID"; return 1; }
    valid_active_state "$REPORT_TIMER_ACTIVE_BEFORE" || { fail_at "REPORT_ACTIVE_STATE_INVALID"; return 1; }

    for file in "${RUNTIME_UPDATE_FILES[@]}"; do
        require_regular "$BACKUP_DIR/runtime/$file" "BACKUP_RUNTIME_MISSING_$file" || return 1
    done
    require_regular "$BACKUP_DIR/runtime/.teddy-stage9-commit" "BACKUP_STAGE9_MARKER_MISSING" || return 1
    require_regular "$BACKUP_DIR/runtime/.teddy-stage10-b3-commit" "BACKUP_STAGE10_B3_MARKER_MISSING" || return 1
    require_regular "$BACKUP_DIR/etc-default/teddy-discovery.metadata" "BACKUP_ENVIRONMENT_METADATA_MISSING" || return 1

    verify_pre_state_targets || return 1
    verify_current_b4 || return 1
    require_absent "$APPLY_TIMER" "APPLY_TIMER_PRESENT" || return 1
    require_absent "$APPLY_SERVICE_DROPIN" "APPLY_SERVICE_DROPIN_PRESENT" || return 1
    quiesce || return 1
    restore_runtime || return 1
    systemctl daemon-reload >"$BACKUP_DIR/rollback-daemon-reload.txt" 2>&1 || { fail_at "ROLLBACK_DAEMON_RELOAD_FAILED"; return 1; }

    restore_enabled_state "$STAGE9_TIMER_NAME" "$STAGE9_TIMER_ENABLED_BEFORE" || { fail_at "STAGE9_ENABLED_RESTORE_FAILED"; return 1; }
    restore_enabled_state "$REPORT_TIMER_NAME" "$REPORT_TIMER_ENABLED_BEFORE" || { fail_at "REPORT_ENABLED_RESTORE_FAILED"; return 1; }
    restore_active_timers || { fail_at "TIMER_ACTIVE_RESTORE_FAILED"; return 1; }
    verify_pre_state_targets || { fail_at "EXISTING_ARTIFACT_CHANGED_AFTER_ROLLBACK"; return 1; }
    [ "$(unit_state is-enabled "$STAGE9_TIMER_NAME")" = "$STAGE9_TIMER_ENABLED_BEFORE" ] || { fail_at "STAGE9_ENABLED_FINAL_MISMATCH"; return 1; }
    [ "$(unit_state is-enabled "$REPORT_TIMER_NAME")" = "$REPORT_TIMER_ENABLED_BEFORE" ] || { fail_at "REPORT_ENABLED_FINAL_MISMATCH"; return 1; }
    [ "$(unit_state is-active "$STAGE9_TIMER_NAME")" = "$STAGE9_TIMER_ACTIVE_BEFORE" ] || { fail_at "STAGE9_ACTIVE_FINAL_MISMATCH"; return 1; }
    [ "$(unit_state is-active "$REPORT_TIMER_NAME")" = "$REPORT_TIMER_ACTIVE_BEFORE" ] || { fail_at "REPORT_ACTIVE_FINAL_MISMATCH"; return 1; }
    require_absent "$RUNTIME_DIR/teddy_discovery_jav_reconcile_apply.py" "B4_RUNTIME_REMAINS" || return 1
    require_absent "$APPLY_WRAPPER" "B4_WRAPPER_REMAINS" || return 1
    require_absent "$APPLY_SERVICE" "B4_SERVICE_REMAINS" || return 1
    require_absent "$APPLY_TIMER" "B4_TIMER_REMAINS" || return 1
    require_absent "$APPLY_SERVICE_DROPIN" "B4_SERVICE_DROPIN_REMAINS" || return 1
    return 0
}


run()
{
    local main_rc cleanup_rc
    main "$@"
    main_rc=$?
    CLEANUP_OUTPUT=0
    cleanup_timers
    cleanup_rc=$?
    if [ "$main_rc" -ne 0 ]; then
        failure_report
        return "$main_rc"
    fi
    if [ "$cleanup_rc" -ne 0 ]; then
        FAILURE_POINT="TIMER_FINALIZER_FAILED"
        failure_report
        return 1
    fi
    success_report
    return 0
}


if [ "${STAGE10_B4_LIBRARY_ONLY:-0}" != "1" ]; then
    trap cleanup_timers EXIT
    run "$@"
fi
