#!/usr/bin/env bash
set -u
set -o pipefail


EXPECTED_HEAD="af64cd4937b52fd70d25489be2e62458669d489c"

PRODUCTION_ROOT="/opt/missav-dlp-web"
RUNTIME_DIR="$PRODUCTION_ROOT/stage9-runtime"
ENV_FILE="/etc/default/teddy-discovery"
STAGE10_MARKER="$RUNTIME_DIR/.teddy-stage10-b3-commit"

STAGE9_WRAPPER="/usr/local/sbin/teddy-completion-stage9-runner"
STAGE9_SERVICE="/etc/systemd/system/teddy-completion-stage9.service"
STAGE9_TIMER="/etc/systemd/system/teddy-completion-stage9.timer"
STAGE9_TIMER_NAME="teddy-completion-stage9.timer"
STAGE9_SERVICE_NAME="teddy-completion-stage9.service"

REPORT_WRAPPER="/usr/local/sbin/teddy-discovery-jav-reconcile-report"
REPORT_SERVICE="/etc/systemd/system/teddy-discovery-jav-reconcile.service"
REPORT_TIMER="/etc/systemd/system/teddy-discovery-jav-reconcile.timer"
REPORT_TIMER_NAME="teddy-discovery-jav-reconcile.timer"
REPORT_SERVICE_NAME="teddy-discovery-jav-reconcile.service"

UPDATE_FILES=(
    "teddy_discovery_completion_orchestrator.py"
    "teddy_discovery_completion_runner.py"
    "teddy_discovery_import.py"
    "teddy_discovery_media_publish.py"
)

ADD_RUNTIME_FILES=(
    "teddy_discovery_jav_reconcile_report.py"
    "teddy_discovery_jav_reconcile.py"
    "teddy_discovery_operation_lock.py"
)

BACKUP_DIR="${1:-}"
FAILURE_POINT=""
STAGE9_TIMER_ENABLED_BEFORE="UNKNOWN"
STAGE9_TIMER_ACTIVE_BEFORE="UNKNOWN"
ENV_FILE_PRESENT_BEFORE=0
STAGE10_MARKER_PRESENT_BEFORE="UNKNOWN"


failure_report()
{
    printf '%s\n' "RESULT=FAIL"
    printf '%s\n' "FAILURE_POINT=${FAILURE_POINT:-UNKNOWN}"
    printf '%s\n' "BACKUP_DIR=${BACKUP_DIR:-UNAVAILABLE}"
    printf '%s\n' "REPORT_TIMER=ROLLBACK_STOPPED"
}


fail_at()
{
    FAILURE_POINT=$1
    failure_report
    return 1
}


unit_state()
{
    systemctl "$1" "$2" 2>&1
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


valid_stage10_marker()
{
    if [ ! -f "$STAGE10_MARKER" ] || [ -L "$STAGE10_MARKER" ]; then
        return 1
    fi

    if [ "$(stat -c '%u:%g %a' "$STAGE10_MARKER")" != "0:0 0644" ]; then
        return 1
    fi

    if [ "$(stat -c '%s' "$STAGE10_MARKER")" != "41" ]; then
        return 1
    fi

    [ "$(cat "$STAGE10_MARKER")" = "$EXPECTED_HEAD" ]
}


atomic_restore()
{
    source_path=$1
    target_path=$2
    mode=$3
    temp_path="${target_path}.stage10-b3-rollback.$$"

    if [ ! -f "$source_path" ]; then
        return 1
    fi

    rm -f -- "$temp_path"
    install \
        -o root \
        -g root \
        -m "$mode" \
        -- "$source_path" "$temp_path" || {
            rm -f -- "$temp_path"
            return 1
        }

    mv -f -- "$temp_path" "$target_path" || {
        rm -f -- "$temp_path"
        return 1
    }

    return 0
}


state_value()
{
    awk -F= -v wanted="$1" '$1 == wanted { value = $2 } END { print value }' "$BACKUP_DIR/pre-state.txt"
}


main()
{
    umask 077

    if [ "$(id -u)" -ne 0 ]; then
        fail_at "ROOT_REQUIRED"
        return 1
    fi

    for command_name in systemctl install mv rm awk id sleep basename stat cat; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            fail_at "MISSING_COMMAND_$command_name"
            return 1
        fi
    done

    case "$BACKUP_DIR" in
        /opt/missav-dlp-web/backups/stage10-b3-????????-??????)
            ;;
        *)
            fail_at "BACKUP_DIR_PATH_INVALID"
            return 1
            ;;
    esac

    if [ ! -d "$BACKUP_DIR" ]; then
        fail_at "BACKUP_DIR_REQUIRED"
        return 1
    fi

    if [ ! -f "$BACKUP_DIR/pre-state.txt" ]; then
        fail_at "PRE_STATE_MISSING"
        return 1
    fi

    STAGE9_TIMER_ENABLED_BEFORE=$(state_value stage9_timer_enabled_before)
    STAGE9_TIMER_ACTIVE_BEFORE=$(state_value stage9_timer_active_before)
    ENV_FILE_PRESENT_BEFORE=$(state_value environment_file_present_before)
    STAGE10_MARKER_PRESENT_BEFORE=$(state_value stage10_b3_marker_present_before)

    case "$STAGE9_TIMER_ENABLED_BEFORE" in
        enabled|enabled-runtime|disabled|static|indirect|masked|generated|transient|not-found)
            ;;
        *)
            fail_at "BACKUP_STAGE9_ENABLED_STATE_INVALID"
            return 1
            ;;
    esac

    case "$STAGE9_TIMER_ACTIVE_BEFORE" in
        active|inactive|failed|activating|deactivating|unknown)
            ;;
        *)
            fail_at "BACKUP_STAGE9_ACTIVE_STATE_INVALID"
            return 1
            ;;
    esac

    case "$ENV_FILE_PRESENT_BEFORE" in
        0|1)
            ;;
        *)
            fail_at "BACKUP_ENVIRONMENT_STATE_INVALID"
            return 1
            ;;
    esac

    if [ "$STAGE10_MARKER_PRESENT_BEFORE" != "0" ]; then
        fail_at "BACKUP_STAGE10_B3_MARKER_STATE_INVALID"
        return 1
    fi

    for file in "${UPDATE_FILES[@]}"; do
        if [ ! -f "$BACKUP_DIR/runtime/$file" ]; then
            fail_at "BACKUP_RUNTIME_MISSING_$file"
            return 1
        fi
    done

    for file in \
        "$BACKUP_DIR/stage9/teddy-completion-stage9-runner" \
        "$BACKUP_DIR/systemd/teddy-completion-stage9.service" \
        "$BACKUP_DIR/systemd/teddy-completion-stage9.timer"; do
        if [ ! -f "$file" ]; then
            fail_at "BACKUP_STAGE9_FILE_MISSING_$(basename -- "$file")"
            return 1
        fi
    done

    if [ "$ENV_FILE_PRESENT_BEFORE" = "1" ] && \
        [ ! -f "$BACKUP_DIR/etc/default/teddy-discovery" ]; then
        fail_at "BACKUP_ENVIRONMENT_FILE_MISSING"
        return 1
    fi

    report_timer_state=$(unit_state is-active "$REPORT_TIMER_NAME")
    if ! valid_active_state "$report_timer_state"; then
        fail_at "REPORT_TIMER_ACTIVE_STATE_UNREADABLE"
        return 1
    fi
    if [ "$report_timer_state" = "active" ]; then
        systemctl stop "$REPORT_TIMER_NAME" >"$BACKUP_DIR/rollback-report-timer-stop.txt" 2>&1
        if [ "$?" -ne 0 ]; then
            fail_at "REPORT_TIMER_STOP_FAILED"
            return 1
        fi
    fi

    report_service_state=$(unit_state is-active "$REPORT_SERVICE_NAME")
    if ! valid_active_state "$report_service_state"; then
        fail_at "REPORT_SERVICE_ACTIVE_STATE_UNREADABLE"
        return 1
    fi
    if [ "$report_service_state" = "active" ]; then
        systemctl stop "$REPORT_SERVICE_NAME" >"$BACKUP_DIR/rollback-report-service-stop.txt" 2>&1
        if [ "$?" -ne 0 ]; then
            fail_at "REPORT_SERVICE_STOP_FAILED"
            return 1
        fi
    fi

    report_timer_enabled=$(unit_state is-enabled "$REPORT_TIMER_NAME")
    if ! valid_enabled_state "$report_timer_enabled"; then
        fail_at "REPORT_TIMER_ENABLED_STATE_UNREADABLE"
        return 1
    fi
    case "$report_timer_enabled" in
        enabled|enabled-runtime|indirect)
            systemctl disable "$REPORT_TIMER_NAME" >"$BACKUP_DIR/rollback-report-timer-disable.txt" 2>&1
            if [ "$?" -ne 0 ]; then
                fail_at "REPORT_TIMER_DISABLE_FAILED"
                return 1
            fi
            ;;
    esac

    stage9_timer_state=$(unit_state is-active "$STAGE9_TIMER_NAME")
    if ! valid_active_state "$stage9_timer_state"; then
        fail_at "STAGE9_TIMER_ACTIVE_STATE_UNREADABLE"
        return 1
    fi
    if [ "$stage9_timer_state" = "active" ]; then
        systemctl stop "$STAGE9_TIMER_NAME" >"$BACKUP_DIR/rollback-stage9-timer-stop.txt" 2>&1
        if [ "$?" -ne 0 ]; then
            fail_at "STAGE9_TIMER_STOP_FAILED"
            return 1
        fi
    fi

    wait_seconds=0
    while :; do
        service_state=$(unit_state is-active "$STAGE9_SERVICE_NAME")
        case "$service_state" in
            active|activating|deactivating)
                if [ "$wait_seconds" -ge 120 ]; then
                    fail_at "STAGE9_SERVICE_DID_NOT_QUIESCE"
                    return 1
                fi
                sleep 1
                wait_seconds=$((wait_seconds + 1))
                ;;
            inactive|failed)
                break
                ;;
            *)
                fail_at "STAGE9_SERVICE_STATE_UNREADABLE_DURING_QUIESCE"
                return 1
                ;;
        esac
    done

    for file in "${UPDATE_FILES[@]}"; do
        if ! atomic_restore \
            "$BACKUP_DIR/runtime/$file" \
            "$RUNTIME_DIR/$file" \
            0644; then
            fail_at "RUNTIME_RESTORE_FAILED_$file"
            return 1
        fi
    done

    for file in "${ADD_RUNTIME_FILES[@]}"; do
        rm -f -- "$RUNTIME_DIR/$file"
        if [ -e "$RUNTIME_DIR/$file" ]; then
            fail_at "RUNTIME_ADD_REMOVE_FAILED_$file"
            return 1
        fi
    done

    if [ -L "$STAGE10_MARKER" ] || \
        { [ -e "$STAGE10_MARKER" ] && ! valid_stage10_marker; }; then
        fail_at "STAGE10_B3_MARKER_UNEXPECTED"
        return 1
    fi

    rm -f -- "$STAGE10_MARKER"
    if [ -e "$STAGE10_MARKER" ] || [ -L "$STAGE10_MARKER" ]; then
        fail_at "STAGE10_B3_MARKER_REMOVE_FAILED"
        return 1
    fi

    if ! atomic_restore \
        "$BACKUP_DIR/stage9/teddy-completion-stage9-runner" \
        "$STAGE9_WRAPPER" \
        0755; then
        fail_at "STAGE9_WRAPPER_RESTORE_FAILED"
        return 1
    fi

    if ! atomic_restore \
        "$BACKUP_DIR/systemd/teddy-completion-stage9.service" \
        "$STAGE9_SERVICE" \
        0644; then
        fail_at "STAGE9_SERVICE_RESTORE_FAILED"
        return 1
    fi

    if ! atomic_restore \
        "$BACKUP_DIR/systemd/teddy-completion-stage9.timer" \
        "$STAGE9_TIMER" \
        0644; then
        fail_at "STAGE9_TIMER_RESTORE_FAILED"
        return 1
    fi

    if [ -f "$BACKUP_DIR/runtime/.teddy-stage9-commit" ]; then
        if ! atomic_restore \
            "$BACKUP_DIR/runtime/.teddy-stage9-commit" \
            "$RUNTIME_DIR/.teddy-stage9-commit" \
            0644; then
            fail_at "PROVENANCE_MARKER_RESTORE_FAILED"
            return 1
        fi
    fi

    rm -f -- "$REPORT_WRAPPER" "$REPORT_SERVICE" "$REPORT_TIMER"
    if [ -e "$REPORT_WRAPPER" ] || [ -e "$REPORT_SERVICE" ] || [ -e "$REPORT_TIMER" ]; then
        fail_at "REPORT_ARTIFACT_REMOVE_FAILED"
        return 1
    fi

    if [ "$ENV_FILE_PRESENT_BEFORE" = "1" ]; then
        if ! atomic_restore \
            "$BACKUP_DIR/etc/default/teddy-discovery" \
            "$ENV_FILE" \
            0600; then
            fail_at "ENVIRONMENT_FILE_RESTORE_FAILED"
            return 1
        fi
    else
        rm -f -- "$ENV_FILE"
        if [ -e "$ENV_FILE" ]; then
            fail_at "ENVIRONMENT_FILE_REMOVE_FAILED"
            return 1
        fi
    fi

    systemctl daemon-reload >"$BACKUP_DIR/rollback-daemon-reload.txt" 2>&1
    if [ "$?" -ne 0 ]; then
        fail_at "ROLLBACK_DAEMON_RELOAD_FAILED"
        return 1
    fi

    current_enabled=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    if ! valid_enabled_state "$current_enabled"; then
        fail_at "STAGE9_TIMER_ENABLED_STATE_UNREADABLE_DURING_RESTORE"
        return 1
    fi
    if [ "$STAGE9_TIMER_ENABLED_BEFORE" = "enabled" ] && [ "$current_enabled" != "enabled" ]; then
        systemctl enable "$STAGE9_TIMER_NAME" >"$BACKUP_DIR/rollback-stage9-enable.txt" 2>&1
        if [ "$?" -ne 0 ]; then
            fail_at "STAGE9_TIMER_ENABLE_RESTORE_FAILED"
            return 1
        fi
    elif [ "$STAGE9_TIMER_ENABLED_BEFORE" != "enabled" ] && [ "$current_enabled" = "enabled" ]; then
        systemctl disable "$STAGE9_TIMER_NAME" >"$BACKUP_DIR/rollback-stage9-disable.txt" 2>&1
        if [ "$?" -ne 0 ]; then
            fail_at "STAGE9_TIMER_DISABLE_RESTORE_FAILED"
            return 1
        fi
    fi

    if [ "$STAGE9_TIMER_ACTIVE_BEFORE" = "active" ]; then
        systemctl start "$STAGE9_TIMER_NAME" >"$BACKUP_DIR/rollback-stage9-timer-start.txt" 2>&1
        if [ "$?" -ne 0 ]; then
            fail_at "STAGE9_TIMER_ACTIVE_RESTORE_FAILED"
            return 1
        fi
    fi

    stage9_enabled_after=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    stage9_active_after=$(unit_state is-active "$STAGE9_TIMER_NAME")
    report_timer_after=$(unit_state is-enabled "$REPORT_TIMER_NAME")

    if ! valid_enabled_state "$stage9_enabled_after" || \
        ! valid_active_state "$stage9_active_after" || \
        ! valid_enabled_state "$report_timer_after"; then
        fail_at "ROLLBACK_FINAL_STATE_UNREADABLE"
        return 1
    fi

    if [ "$stage9_enabled_after" != "$STAGE9_TIMER_ENABLED_BEFORE" ] || \
        [ "$stage9_active_after" != "$STAGE9_TIMER_ACTIVE_BEFORE" ]; then
        fail_at "STAGE9_STATE_ROLLBACK_MISMATCH"
        return 1
    fi

    if [ "$report_timer_after" != "not-found" ] && [ "$report_timer_after" != "disabled" ]; then
        fail_at "REPORT_TIMER_ROLLBACK_STATE_MISMATCH"
        return 1
    fi

    printf '%s\n' "RESULT=PASS"
    printf '%s\n' "BACKUP_DIR=$BACKUP_DIR"
    printf '%s\n' "REPORT_TIMER=REMOVED"
    printf '%s\n' "STAGE9_TIMER_ENABLED_BEFORE=$STAGE9_TIMER_ENABLED_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ENABLED_AFTER=$stage9_enabled_after"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_BEFORE=$STAGE9_TIMER_ACTIVE_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_AFTER=$stage9_active_after"

    return 0
}


main "$@"
