#!/usr/bin/env bash
set -u
set -o pipefail


EXPECTED_HEAD="af64cd4937b52fd70d25489be2e62458669d489c"

SOURCE_ROOT=${TEDDY_STAGE10_SOURCE_ROOT:-/opt/missav-pwa-holdings-stage10}

PRODUCTION_ROOT="/opt/missav-dlp-web"
RUNTIME_DIR="$PRODUCTION_ROOT/stage9-runtime"
DISCOVERY_DB="$PRODUCTION_ROOT/discovery/teddy-discovery.sqlite3"
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

ENV_FILE="/etc/default/teddy-discovery"
OPERATION_LOCK="/run/lock/teddy-discovery-jav-library-operation.lock"

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

REPORT_DEPENDENCY_FILES=(
    "teddy_discovery_completion_ssh.py"
    "teddy_discovery_ids.py"
    "teddy_discovery_db.py"
    "teddy_discovery_media_metadata.py"
    "teddy_discovery_organizer.py"
    "teddy_discovery_organizer_apply.py"
)

BACKUP_DIR="UNAVAILABLE"
FAILURE_POINT=""
STAGE9_TIMER_ENABLED_BEFORE="UNKNOWN"
STAGE9_TIMER_ACTIVE_BEFORE="UNKNOWN"
STAGE9_SERVICE_ACTIVE_BEFORE="UNKNOWN"
STAGE9_TIMER_ENABLED_AFTER="UNKNOWN"
STAGE9_TIMER_ACTIVE_AFTER="UNKNOWN"
CONTAINER_RUNNING_BEFORE="UNKNOWN"
ENV_FILE_PRESENT_BEFORE=0
STAGE10_MARKER_PRESENT_BEFORE=0
STAGE9_TIMER_STOP_ATTEMPTED=0
STAGE9_TIMER_RESTORED=0
CLEANUP_DONE=0
CLEANUP_STATUS="NOT_REQUIRED"
CLEANUP_OUTPUT=1


failure_report()
{
    printf '%s\n' "RESULT=FAIL"
    printf '%s\n' "FAILURE_POINT=${FAILURE_POINT:-UNKNOWN}"
    printf '%s\n' "BACKUP_DIR=$BACKUP_DIR"
    printf '%s\n' "STAGE9_TIMER_ENABLED_BEFORE=$STAGE9_TIMER_ENABLED_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_BEFORE=$STAGE9_TIMER_ACTIVE_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ENABLED_AFTER=$STAGE9_TIMER_ENABLED_AFTER"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_AFTER=$STAGE9_TIMER_ACTIVE_AFTER"
    printf '%s\n' "REPORT_TIMER_ENABLED=NO"
    printf '%s\n' "TIMER_ENABLE=SKIPPED"
    printf '%s\n' "STAGE9_TIMER_CLEANUP=$CLEANUP_STATUS"
    if [ "$CLEANUP_STATUS" = "FAIL" ]; then
        printf '%s\n' "HIGH_PRIORITY=STAGE9_TIMER_RESTORE_FAILED"
    fi
}


success_report()
{
    printf '%s\n' "RESULT=PASS"
    printf '%s\n' "BACKUP_DIR=$BACKUP_DIR"
    printf '%s\n' "STAGE9_TIMER_ENABLED_BEFORE=$STAGE9_TIMER_ENABLED_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ENABLED_AFTER=$STAGE9_TIMER_ENABLED_AFTER"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_BEFORE=$STAGE9_TIMER_ACTIVE_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_AFTER=$STAGE9_TIMER_ACTIVE_AFTER"
    printf '%s\n' "CONTAINER_RUNNING_BEFORE=$CONTAINER_RUNNING_BEFORE"
    printf '%s\n' "REPORT_TIMER_ENABLED=NO"
    printf '%s\n' "CANARY_RESULT=PASS"
    printf '%s\n' "FILESYSTEM_COUNT=$CANARY_FILESYSTEM_COUNT"
    printf '%s\n' "DB_PRESENT_COUNT=$CANARY_DB_PRESENT_COUNT"
    printf '%s\n' "FINDING_TOTAL=$CANARY_FINDING_TOTAL"
    printf '%s\n' "APPLY=$CANARY_APPLY"
    printf '%s\n' "DB_BYTE_UNCHANGED=PASS"
}


fail_at()
{
    FAILURE_POINT=$1
    return 1
}


cleanup_stage9_timer()
{
    if [ "$CLEANUP_DONE" -eq 1 ]; then
        return 0
    fi

    CLEANUP_DONE=1

    if [ "$STAGE9_TIMER_STOP_ATTEMPTED" -ne 1 ] || \
        [ "$STAGE9_TIMER_RESTORED" -eq 1 ]; then
        return 0
    fi

    cleanup_log=/dev/null
    if [ -d "$BACKUP_DIR" ]; then
        cleanup_log="$BACKUP_DIR/stage9-finalizer.txt"
    fi

    systemctl start "$STAGE9_TIMER_NAME" >"$cleanup_log" 2>&1
    cleanup_start_rc=$?
    if [ "$cleanup_start_rc" -ne 0 ]; then
        STAGE9_TIMER_ACTIVE_AFTER=$(unit_state is-active "$STAGE9_TIMER_NAME")
        CLEANUP_STATUS="FAIL"
        if [ "$CLEANUP_OUTPUT" -eq 1 ]; then
            printf '%s\n' "STAGE9_TIMER_CLEANUP=FAIL"
            printf '%s\n' "HIGH_PRIORITY=STAGE9_TIMER_RESTORE_FAILED"
        fi
        return 1
    fi

    cleanup_state=$(unit_state is-active "$STAGE9_TIMER_NAME")
    STAGE9_TIMER_ACTIVE_AFTER="$cleanup_state"
    if [ "$cleanup_state" != "active" ]; then
        CLEANUP_STATUS="FAIL"
        if [ "$CLEANUP_OUTPUT" -eq 1 ]; then
            printf '%s\n' "STAGE9_TIMER_CLEANUP=FAIL"
            printf '%s\n' "HIGH_PRIORITY=STAGE9_TIMER_RESTORE_STATE_NOT_ACTIVE"
        fi
        return 1
    fi

    STAGE9_TIMER_RESTORED=1
    CLEANUP_STATUS="PASS"
    if [ "$CLEANUP_OUTPUT" -eq 1 ]; then
        printf '%s\n' "STAGE9_TIMER_CLEANUP=PASS"
    fi
    return 0
}


trap cleanup_stage9_timer EXIT


require_command()
{
    if ! command -v "$1" >/dev/null 2>&1; then
        fail_at "MISSING_COMMAND_$1"
        return 1
    fi

    return 0
}


require_file()
{
    if [ ! -f "$1" ]; then
        fail_at "$2"
        return 1
    fi

    return 0
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


extract_stage9_arg()
{
    awk -v wanted="$1" '
        {
            for (field = 1; field < NF && !found; field++) {
                if ($field == wanted) {
                    print $(field + 1)
                    found = 1
                }
            }
        }
    ' "$STAGE9_WRAPPER"
}


valid_env_value()
{
    case "$1" in
        ""|*[[:space:]=]*)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}


valid_sha256()
{
    printf '%s\n' "$1" | grep -Eq '^[0-9a-f]{64}$'
}


backup_file()
{
    source_path=$1
    backup_path=$2

    if [ ! -e "$source_path" ]; then
        return 0
    fi

    mkdir -p "$(dirname -- "$backup_path")" || return 1
    cp -a -- "$source_path" "$backup_path" || return 1
    return 0
}


verify_target()
{
    target_path=$1
    expected_mode=${2#0}
    actual_state=$(stat -c '%u:%g %a' "$target_path" 2>/dev/null)
    [ "$actual_state" = "0:0 $expected_mode" ]
}


verify_environment_file()
{
    if ! verify_target "$ENV_FILE" 0600; then
        return 1
    fi

    [ "$(awk -F= '
        NF == 2 && $1 == "TEDDY_FINAL_SSH_HOST" { host++ }
        NF == 2 && $1 == "TEDDY_FINAL_SSH_USER" { user++ }
        NF == 2 && $1 == "TEDDY_FINAL_SSH_KEY" { key++ }
        NF == 2 && $1 == "TEDDY_FINAL_SSH_KNOWN_HOSTS" { known_hosts++ }
        END {
            print (host == 1 && user == 1 && key == 1 && known_hosts == 1)
        }
    ' "$ENV_FILE")" = "1" ]
}


allowed_source_worktree_status()
{
    awk '
        $0 == "?? deploy/stage10-b3/install-stage10-b3-report-only.sh" ||
        $0 == "?? deploy/stage10-b3/rollback-stage10-b3.sh" {
            next
        }
        { unexpected = 1 }
        END { print (unexpected ? "FAIL" : "PASS") }
    '
}


atomic_install()
{
    source_path=$1
    target_path=$2
    mode=$3
    temp_path="${target_path}.stage10-b3.$$"

    rm -f -- "$temp_path"

    install \
        -o root \
        -g root \
        -m "$mode" \
        -- "$source_path" "$temp_path" || {
            rm -f -- "$temp_path"
            return 1
        }

    source_hash=$(sha256sum "$source_path" | awk '{print $1}')
    temp_hash=$(sha256sum "$temp_path" | awk '{print $1}')

    if [ -z "$source_hash" ] || [ "$source_hash" != "$temp_hash" ]; then
        rm -f -- "$temp_path"
        return 1
    fi

    mv -f -- "$temp_path" "$target_path" || {
        rm -f -- "$temp_path"
        return 1
    }

    return 0
}


install_provenance_marker()
{
    temp_path="${STAGE10_MARKER}.stage10-b3.$$"

    rm -f -- "$temp_path"

    printf '%s\n' "$EXPECTED_HEAD" >"$temp_path" || {
        rm -f -- "$temp_path"
        return 1
    }

    chown root:root "$temp_path" || {
        rm -f -- "$temp_path"
        return 1
    }

    chmod 0644 "$temp_path" || {
        rm -f -- "$temp_path"
        return 1
    }

    mv -f -- "$temp_path" "$STAGE10_MARKER" || {
        rm -f -- "$temp_path"
        return 1
    }

    return 0
}


verify_provenance_marker()
{
    if ! verify_target "$STAGE10_MARKER" 0644; then
        return 1
    fi

    if [ "$(stat -c '%s' "$STAGE10_MARKER")" != "41" ]; then
        return 1
    fi

    [ "$(cat "$STAGE10_MARKER")" = "$EXPECTED_HEAD" ]
}


write_environment_file()
{
    temp_path="${ENV_FILE}.stage10-b3.$$"

    rm -f -- "$temp_path"

    {
        printf 'TEDDY_FINAL_SSH_HOST=%s\n' "$SSH_HOST"
        printf 'TEDDY_FINAL_SSH_USER=%s\n' "$SSH_USER"
        printf 'TEDDY_FINAL_SSH_KEY=%s\n' "$SSH_KEY"
        printf 'TEDDY_FINAL_SSH_KNOWN_HOSTS=%s\n' "$SSH_KNOWN_HOSTS"
    } > "$temp_path" || {
        rm -f -- "$temp_path"
        return 1
    }

    chown root:root "$temp_path" || {
        rm -f -- "$temp_path"
        return 1
    }

    chmod 0600 "$temp_path" || {
        rm -f -- "$temp_path"
        return 1
    }

    mv -f -- "$temp_path" "$ENV_FILE" || {
        rm -f -- "$temp_path"
        return 1
    }

    return 0
}


record_source_hashes()
{
    {
        printf 'HEAD=%s\n' "$HEAD"
        for file in "${UPDATE_FILES[@]}" "${ADD_RUNTIME_FILES[@]}" "${REPORT_DEPENDENCY_FILES[@]}"; do
            sha256sum "$SOURCE_ROOT/$file"
        done
        sha256sum \
            "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-report" \
            "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile.service" \
            "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile.timer"
    } > "$BACKUP_DIR/source-sha256.txt"
}


main()
{
    umask 077

    if [ "$(id -u)" -ne 0 ]; then
        fail_at "ROOT_REQUIRED"
        return 1
    fi

    for command_name in git systemctl install mv rm cp sha256sum awk python3 bash journalctl date grep mkdir chown chmod stat sleep id basename cat; do
        if ! require_command "$command_name"; then
            return 1
        fi
    done

    if [ ! -d "$SOURCE_ROOT/.git" ] && [ ! -f "$SOURCE_ROOT/.git" ]; then
        fail_at "SOURCE_ROOT_NOT_GIT_WORKTREE"
        return 1
    fi

    HEAD=$(git -C "$SOURCE_ROOT" rev-parse HEAD 2>/dev/null)
    HEAD_RC=$?

    if [ "$HEAD_RC" -ne 0 ] || [ "$HEAD" != "$EXPECTED_HEAD" ]; then
        fail_at "SOURCE_HEAD_MISMATCH"
        return 1
    fi

    WORKTREE_STATUS=$(git -C "$SOURCE_ROOT" status --porcelain=v1 --untracked-files=all 2>&1)
    WORKTREE_RC=$?

    if [ "$WORKTREE_RC" -ne 0 ]; then
        fail_at "SOURCE_WORKTREE_STATUS_UNREADABLE"
        return 1
    fi

    if [ -n "$WORKTREE_STATUS" ] && \
        [ "$(printf '%s\n' "$WORKTREE_STATUS" | allowed_source_worktree_status)" != "PASS" ]; then
        fail_at "SOURCE_WORKTREE_NOT_CLEAN"
        return 1
    fi

    for file in "${UPDATE_FILES[@]}" "${ADD_RUNTIME_FILES[@]}" "${REPORT_DEPENDENCY_FILES[@]}"; do
        if ! require_file "$SOURCE_ROOT/$file" "SOURCE_MISSING_$file"; then
            return 1
        fi
    done

    for file in \
        deploy/systemd/teddy-discovery-jav-reconcile-report \
        deploy/systemd/teddy-discovery-jav-reconcile.service \
        deploy/systemd/teddy-discovery-jav-reconcile.timer; do
        if ! require_file "$SOURCE_ROOT/$file" "DEPLOY_SOURCE_MISSING_$file"; then
            return 1
        fi
    done

    if ! grep -Fq '"/run/lock/teddy-discovery-jav-library-operation.lock"' \
        "$SOURCE_ROOT/teddy_discovery_operation_lock.py"; then
        fail_at "OPERATION_LOCK_PATH_SOURCE_MISMATCH"
        return 1
    fi

    for file in "${UPDATE_FILES[@]}"; do
        if ! require_file "$RUNTIME_DIR/$file" "PRODUCTION_RUNTIME_MISSING_$file"; then
            return 1
        fi
    done

    if [ -e "$STAGE10_MARKER" ] || [ -L "$STAGE10_MARKER" ]; then
        fail_at "PRODUCTION_STAGE10_B3_MARKER_ALREADY_EXISTS"
        return 1
    fi
    STAGE10_MARKER_PRESENT_BEFORE=0

    if ! require_file "$STAGE9_WRAPPER" "PRODUCTION_STAGE9_WRAPPER_MISSING"; then
        return 1
    fi

    if ! require_file "$STAGE9_SERVICE" "PRODUCTION_STAGE9_SERVICE_MISSING"; then
        return 1
    fi

    if ! require_file "$STAGE9_TIMER" "PRODUCTION_STAGE9_TIMER_MISSING"; then
        return 1
    fi

    if ! grep -Fq "ExecStart=$STAGE9_WRAPPER" "$STAGE9_SERVICE"; then
        fail_at "STAGE9_SERVICE_EXECSTART_MISMATCH"
        return 1
    fi

    if ! grep -Fq 'RUNTIME="/opt/missav-dlp-web/stage9-runtime"' "$STAGE9_WRAPPER"; then
        fail_at "STAGE9_WRAPPER_RUNTIME_MISMATCH"
        return 1
    fi

    for file in "${ADD_RUNTIME_FILES[@]}"; do
        if [ -e "$RUNTIME_DIR/$file" ]; then
            fail_at "PRODUCTION_ADD_TARGET_ALREADY_EXISTS_$file"
            return 1
        fi
    done

    for path in "$REPORT_WRAPPER" "$REPORT_SERVICE" "$REPORT_TIMER"; do
        if [ -e "$path" ]; then
            fail_at "REPORT_TARGET_ALREADY_EXISTS_$path"
            return 1
        fi
    done

    SSH_HOST=$(extract_stage9_arg --host)
    SSH_USER=$(extract_stage9_arg --user)
    SSH_KEY=$(extract_stage9_arg --key)
    SSH_KNOWN_HOSTS=$(extract_stage9_arg --known-hosts)

    for value in "$SSH_HOST" "$SSH_USER" "$SSH_KEY" "$SSH_KNOWN_HOSTS"; do
        if ! valid_env_value "$value"; then
            fail_at "STAGE9_SSH_CONFIG_INVALID"
            return 1
        fi
    done

    if [ ! -f "$SSH_KEY" ]; then
        fail_at "STAGE9_SSH_KEY_MISSING"
        return 1
    fi

    if [ ! -f "$SSH_KNOWN_HOSTS" ]; then
        fail_at "STAGE9_SSH_KNOWN_HOSTS_MISSING"
        return 1
    fi

    if [ -e "$ENV_FILE" ]; then
        ENV_FILE_PRESENT_BEFORE=1
    fi

    STAGE9_TIMER_ENABLED_BEFORE=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    STAGE9_TIMER_ENABLED_RC=$?
    STAGE9_TIMER_ACTIVE_BEFORE=$(unit_state is-active "$STAGE9_TIMER_NAME")
    STAGE9_TIMER_ACTIVE_RC=$?
    STAGE9_SERVICE_ACTIVE_BEFORE=$(unit_state is-active "$STAGE9_SERVICE_NAME")
    STAGE9_SERVICE_ACTIVE_RC=$?

    if [ "$STAGE9_TIMER_ENABLED_RC" -ne 0 ] || ! valid_enabled_state "$STAGE9_TIMER_ENABLED_BEFORE"; then
        fail_at "STAGE9_TIMER_ENABLED_STATE_UNREADABLE"
        return 1
    fi

    if [ "$STAGE9_TIMER_ENABLED_BEFORE" != "enabled" ] && [ "$STAGE9_TIMER_ENABLED_BEFORE" != "enabled-runtime" ]; then
        fail_at "STAGE9_TIMER_NOT_ENABLED"
        return 1
    fi

    if [ "$STAGE9_TIMER_ACTIVE_RC" -ne 0 ] && [ "$STAGE9_TIMER_ACTIVE_BEFORE" != "inactive" ] && [ "$STAGE9_TIMER_ACTIVE_BEFORE" != "failed" ]; then
        fail_at "STAGE9_TIMER_ACTIVE_STATE_UNREADABLE"
        return 1
    fi

    if ! valid_active_state "$STAGE9_TIMER_ACTIVE_BEFORE"; then
        fail_at "STAGE9_TIMER_ACTIVE_STATE_INVALID"
        return 1
    fi

    if [ "$STAGE9_SERVICE_ACTIVE_RC" -ne 0 ] && [ "$STAGE9_SERVICE_ACTIVE_BEFORE" != "inactive" ] && [ "$STAGE9_SERVICE_ACTIVE_BEFORE" != "failed" ]; then
        fail_at "STAGE9_SERVICE_ACTIVE_STATE_UNREADABLE"
        return 1
    fi

    if ! valid_active_state "$STAGE9_SERVICE_ACTIVE_BEFORE"; then
        fail_at "STAGE9_SERVICE_ACTIVE_STATE_INVALID"
        return 1
    fi

    if command -v docker >/dev/null 2>&1; then
        CONTAINER_RUNNING_BEFORE=$(docker inspect --format '{{.State.Running}}' missav-dlp-web 2>&1)
        CONTAINER_RUNNING_RC=$?
        if [ "$CONTAINER_RUNNING_RC" -ne 0 ]; then
            CONTAINER_RUNNING_BEFORE="UNKNOWN"
        fi
    else
        CONTAINER_RUNNING_BEFORE="UNKNOWN_DOCKER_UNAVAILABLE"
    fi

    STAMP=$(date '+%Y%m%d-%H%M%S')
    BACKUP_DIR="$PRODUCTION_ROOT/backups/stage10-b3-$STAMP"

    if [ -e "$BACKUP_DIR" ]; then
        fail_at "BACKUP_DIR_ALREADY_EXISTS"
        return 1
    fi

    mkdir -p \
        "$BACKUP_DIR/runtime" \
        "$BACKUP_DIR/stage9" \
        "$BACKUP_DIR/systemd" \
        "$BACKUP_DIR/etc/default" || {
            fail_at "BACKUP_DIR_CREATE_FAILED"
            return 1
        }

    if ! record_source_hashes; then
        fail_at "SOURCE_HASH_RECORD_FAILED"
        return 1
    fi

    for file in "${UPDATE_FILES[@]}"; do
        if ! backup_file "$RUNTIME_DIR/$file" "$BACKUP_DIR/runtime/$file"; then
            fail_at "BACKUP_RUNTIME_FAILED_$file"
            return 1
        fi
    done

    if ! backup_file "$STAGE9_WRAPPER" "$BACKUP_DIR/stage9/teddy-completion-stage9-runner"; then
        fail_at "BACKUP_STAGE9_WRAPPER_FAILED"
        return 1
    fi

    if ! backup_file "$STAGE9_SERVICE" "$BACKUP_DIR/systemd/teddy-completion-stage9.service"; then
        fail_at "BACKUP_STAGE9_SERVICE_FAILED"
        return 1
    fi

    if ! backup_file "$STAGE9_TIMER" "$BACKUP_DIR/systemd/teddy-completion-stage9.timer"; then
        fail_at "BACKUP_STAGE9_TIMER_FAILED"
        return 1
    fi

    if ! backup_file "$RUNTIME_DIR/.teddy-stage9-commit" "$BACKUP_DIR/runtime/.teddy-stage9-commit"; then
        fail_at "BACKUP_PROVENANCE_MARKER_FAILED"
        return 1
    fi

    if [ "$ENV_FILE_PRESENT_BEFORE" -eq 1 ]; then
        if ! backup_file "$ENV_FILE" "$BACKUP_DIR/etc/default/teddy-discovery"; then
            fail_at "BACKUP_ENVIRONMENT_FILE_FAILED"
            return 1
        fi
    fi

    {
        printf 'source_root=%s\n' "$SOURCE_ROOT"
        printf 'source_head=%s\n' "$HEAD"
        printf 'stage9_timer_enabled_before=%s\n' "$STAGE9_TIMER_ENABLED_BEFORE"
        printf 'stage9_timer_active_before=%s\n' "$STAGE9_TIMER_ACTIVE_BEFORE"
        printf 'stage9_service_active_before=%s\n' "$STAGE9_SERVICE_ACTIVE_BEFORE"
        printf 'container_running_before=%s\n' "$CONTAINER_RUNNING_BEFORE"
        printf 'environment_file_present_before=%s\n' "$ENV_FILE_PRESENT_BEFORE"
        printf 'stage10_b3_marker_present_before=%s\n' "$STAGE10_MARKER_PRESENT_BEFORE"
        printf 'ssh_host_source=%s:--host\n' "$STAGE9_WRAPPER"
        printf 'ssh_user_source=%s:--user\n' "$STAGE9_WRAPPER"
        printf 'ssh_key_source=%s:--key\n' "$STAGE9_WRAPPER"
        printf 'ssh_known_hosts_source=%s:--known-hosts\n' "$STAGE9_WRAPPER"
        printf 'library_root=/volume1/video/video2/JAV\n'
        printf 'operation_lock=%s\n' "$OPERATION_LOCK"
        printf 'report_timer_enable=NOT_PERFORMED\n'
    } > "$BACKUP_DIR/pre-state.txt" || {
        fail_at "PRE_STATE_RECORD_FAILED"
        return 1
    }

    if [ "$STAGE9_TIMER_ACTIVE_BEFORE" = "active" ]; then
        STAGE9_TIMER_STOP_ATTEMPTED=1
        systemctl stop "$STAGE9_TIMER_NAME" >"$BACKUP_DIR/stage9-stop.txt" 2>&1
        STAGE9_STOP_RC=$?
        if [ "$STAGE9_STOP_RC" -ne 0 ]; then
            fail_at "STAGE9_TIMER_STOP_FAILED"
            return 1
        fi
    fi

    wait_seconds=0
    while :; do
        current_service_state=$(unit_state is-active "$STAGE9_SERVICE_NAME")
        case "$current_service_state" in
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

    if ! write_environment_file; then
        fail_at "ENVIRONMENT_FILE_INSTALL_FAILED"
        return 1
    fi

    if ! verify_environment_file; then
        fail_at "ENVIRONMENT_FILE_METADATA_OR_CONTENT_FAILED"
        return 1
    fi

    for file in "${UPDATE_FILES[@]}"; do
        if ! atomic_install "$SOURCE_ROOT/$file" "$RUNTIME_DIR/$file" 0644; then
            fail_at "RUNTIME_UPDATE_FAILED_$file"
            return 1
        fi
    done

    for file in "${ADD_RUNTIME_FILES[@]}"; do
        if ! atomic_install "$SOURCE_ROOT/$file" "$RUNTIME_DIR/$file" 0644; then
            fail_at "RUNTIME_ADD_FAILED_$file"
            return 1
        fi
    done

    for file in "${UPDATE_FILES[@]}" "${ADD_RUNTIME_FILES[@]}"; do
        if ! verify_target "$RUNTIME_DIR/$file" 0644; then
            fail_at "RUNTIME_METADATA_FAILED_$file"
            return 1
        fi
    done

    if ! atomic_install \
        "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-report" \
        "$REPORT_WRAPPER" \
        0755; then
        fail_at "REPORT_WRAPPER_INSTALL_FAILED"
        return 1
    fi

    if ! atomic_install \
        "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile.service" \
        "$REPORT_SERVICE" \
        0644; then
        fail_at "REPORT_SERVICE_INSTALL_FAILED"
        return 1
    fi

    if ! atomic_install \
        "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile.timer" \
        "$REPORT_TIMER" \
        0644; then
        fail_at "REPORT_TIMER_INSTALL_FAILED"
        return 1
    fi

    if ! verify_target "$REPORT_WRAPPER" 0755 || \
        ! verify_target "$REPORT_SERVICE" 0644 || \
        ! verify_target "$REPORT_TIMER" 0644; then
        fail_at "REPORT_METADATA_FAILED"
        return 1
    fi

    if ! grep -Fq 'TEDDY_FINAL_LIBRARY_ROOT=/volume1/video/video2/JAV' "$REPORT_SERVICE"; then
        fail_at "REPORT_LIBRARY_ROOT_UNIT_MISMATCH"
        return 1
    fi

    if grep -Eq 'apply_reconciliation|remote-apply|--apply|import_inventory' "$RUNTIME_DIR/teddy_discovery_jav_reconcile_report.py"; then
        fail_at "REPORT_ONLY_SOURCE_BOUNDARY_FAILED"
        return 1
    fi

    PYTHONPYCACHEPREFIX="$BACKUP_DIR/pycache" \
        python3 -m py_compile \
            "$RUNTIME_DIR/teddy_discovery_completion_orchestrator.py" \
            "$RUNTIME_DIR/teddy_discovery_completion_runner.py" \
            "$RUNTIME_DIR/teddy_discovery_import.py" \
            "$RUNTIME_DIR/teddy_discovery_media_publish.py" \
            "$RUNTIME_DIR/teddy_discovery_jav_reconcile_report.py" \
            "$RUNTIME_DIR/teddy_discovery_jav_reconcile.py" \
            "$RUNTIME_DIR/teddy_discovery_operation_lock.py"
    PYCOMPILE_RC=$?
    if [ "$PYCOMPILE_RC" -ne 0 ]; then
        fail_at "PYCOMPILE_FAILED"
        return 1
    fi

    bash -n "$REPORT_WRAPPER" >"$BACKUP_DIR/report-wrapper-bash-n.txt" 2>&1
    BASH_N_RC=$?
    sh -n "$REPORT_WRAPPER" >"$BACKUP_DIR/report-wrapper-sh-n.txt" 2>&1
    SH_N_RC=$?
    if [ "$BASH_N_RC" -ne 0 ] || [ "$SH_N_RC" -ne 0 ]; then
        fail_at "REPORT_WRAPPER_SYNTAX_FAILED"
        return 1
    fi

    systemd-analyze verify "$REPORT_SERVICE" "$REPORT_TIMER" >"$BACKUP_DIR/systemd-verify.txt" 2>&1
    SYSTEMD_VERIFY_RC=$?
    if [ "$SYSTEMD_VERIFY_RC" -ne 0 ]; then
        fail_at "SYSTEMD_VERIFY_FAILED"
        return 1
    fi

    if ! install_provenance_marker || ! verify_provenance_marker; then
        fail_at "STAGE10_B3_PROVENANCE_MARKER_INSTALL_FAILED"
        return 1
    fi

    systemctl daemon-reload >"$BACKUP_DIR/daemon-reload.txt" 2>&1
    DAEMON_RELOAD_RC=$?
    if [ "$DAEMON_RELOAD_RC" -ne 0 ]; then
        fail_at "SYSTEMD_DAEMON_RELOAD_FAILED"
        return 1
    fi

    if [ "$STAGE9_TIMER_ACTIVE_BEFORE" = "active" ]; then
        systemctl start "$STAGE9_TIMER_NAME" >"$BACKUP_DIR/stage9-restore.txt" 2>&1
        STAGE9_RESTORE_RC=$?
        if [ "$STAGE9_RESTORE_RC" -ne 0 ]; then
            fail_at "STAGE9_TIMER_RESTORE_FAILED"
            return 1
        fi

        STAGE9_TIMER_ACTIVE_AFTER=$(unit_state is-active "$STAGE9_TIMER_NAME")
        if [ "$STAGE9_TIMER_ACTIVE_AFTER" != "active" ]; then
            fail_at "STAGE9_TIMER_RESTORE_STATE_NOT_ACTIVE"
            return 1
        fi
        STAGE9_TIMER_RESTORED=1
    fi

    STAGE9_TIMER_ENABLED_AFTER=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    STAGE9_TIMER_ACTIVE_AFTER=$(unit_state is-active "$STAGE9_TIMER_NAME")

    if [ "$STAGE9_TIMER_ENABLED_AFTER" != "$STAGE9_TIMER_ENABLED_BEFORE" ]; then
        fail_at "STAGE9_TIMER_ENABLED_STATE_CHANGED"
        return 1
    fi

    if [ "$STAGE9_TIMER_ACTIVE_AFTER" != "$STAGE9_TIMER_ACTIVE_BEFORE" ]; then
        fail_at "STAGE9_TIMER_ACTIVE_STATE_CHANGED"
        return 1
    fi

    REPORT_TIMER_ENABLED_AFTER=$(unit_state is-enabled "$REPORT_TIMER_NAME")
    if [ "$REPORT_TIMER_ENABLED_AFTER" != "disabled" ]; then
        fail_at "REPORT_TIMER_NOT_DISABLED"
        return 1
    fi

    if [ ! -f "$DISCOVERY_DB" ]; then
        fail_at "DISCOVERY_DB_MISSING_BEFORE_CANARY"
        return 1
    fi

    DB_SHA_BEFORE=$(sha256sum "$DISCOVERY_DB" | awk '{print $1}')
    if ! valid_sha256 "$DB_SHA_BEFORE"; then
        fail_at "PRODUCTION_DB_HASH_BEFORE_FAILED"
        return 1
    fi
    CANARY_SINCE=$(date --iso-8601=seconds)

    systemctl start "$REPORT_SERVICE_NAME" >"$BACKUP_DIR/canary-start.txt" 2>&1
    CANARY_START_RC=$?

    journalctl \
        --unit="$REPORT_SERVICE_NAME" \
        --since="$CANARY_SINCE" \
        --no-pager \
        --output=cat \
        >"$BACKUP_DIR/canary-journal.txt" 2>&1
    JOURNAL_RC=$?

    CANARY_RESULT=$(awk -F= '$1 == "RESULT" { value = $2 } END { print value }' "$BACKUP_DIR/canary-journal.txt")
    CANARY_SCAN_COMPLETE=$(awk -F= '$1 == "SCAN_COMPLETE" { value = $2 } END { print value }' "$BACKUP_DIR/canary-journal.txt")
    CANARY_ROOT_AVAILABLE=$(awk -F= '$1 == "ROOT_AVAILABLE" { value = $2 } END { print value }' "$BACKUP_DIR/canary-journal.txt")
    CANARY_DB_AVAILABLE=$(awk -F= '$1 == "DB_AVAILABLE" { value = $2 } END { print value }' "$BACKUP_DIR/canary-journal.txt")
    CANARY_FILESYSTEM_COUNT=$(awk -F= '$1 == "FILESYSTEM_COUNT" { value = $2 } END { print value }' "$BACKUP_DIR/canary-journal.txt")
    CANARY_DB_PRESENT_COUNT=$(awk -F= '$1 == "DB_PRESENT_COUNT" { value = $2 } END { print value }' "$BACKUP_DIR/canary-journal.txt")
    CANARY_FINDING_TOTAL=$(awk -F= '$1 == "FINDING_TOTAL" { value = $2 } END { print value }' "$BACKUP_DIR/canary-journal.txt")
    CANARY_APPLY=$(awk -F= '$1 == "APPLY" { value = $2 } END { print value }' "$BACKUP_DIR/canary-journal.txt")

    DB_SHA_AFTER=$(sha256sum "$DISCOVERY_DB" | awk '{print $1}')
    if ! valid_sha256 "$DB_SHA_AFTER"; then
        fail_at "PRODUCTION_DB_HASH_AFTER_FAILED"
        return 1
    fi

    if [ "$CANARY_START_RC" -ne 0 ] || [ "$JOURNAL_RC" -ne 0 ]; then
        fail_at "REPORT_CANARY_COMMAND_FAILED"
        return 1
    fi

    if [ "$CANARY_RESULT" != "PASS" ] || \
        [ "$CANARY_SCAN_COMPLETE" != "1" ] || \
        [ "$CANARY_ROOT_AVAILABLE" != "1" ] || \
        [ "$CANARY_DB_AVAILABLE" != "1" ] || \
        [ "$CANARY_FILESYSTEM_COUNT" != "143" ] || \
        [ "$CANARY_DB_PRESENT_COUNT" != "143" ] || \
        [ "$CANARY_FINDING_TOTAL" != "0" ] || \
        [ "$CANARY_APPLY" != "0" ]; then
        fail_at "REPORT_CANARY_RESULT_MISMATCH"
        return 1
    fi

    if [ -z "$DB_SHA_BEFORE" ] || [ "$DB_SHA_BEFORE" != "$DB_SHA_AFTER" ]; then
        fail_at "PRODUCTION_DB_BYTE_CHANGED"
        return 1
    fi

    REPORT_TIMER_ENABLED_AFTER=$(unit_state is-enabled "$REPORT_TIMER_NAME")
    if [ "$REPORT_TIMER_ENABLED_AFTER" != "disabled" ]; then
        fail_at "REPORT_TIMER_ENABLE_DETECTED"
        return 1
    fi

    return 0
}


run()
{
    main "$@"
    main_rc=$?

    CLEANUP_OUTPUT=0
    cleanup_stage9_timer
    cleanup_rc=$?

    if [ "$main_rc" -ne 0 ]; then
        failure_report
        return "$main_rc"
    fi

    if [ "$cleanup_rc" -ne 0 ]; then
        FAILURE_POINT="STAGE9_TIMER_FINALIZER_FAILED"
        failure_report
        return 1
    fi

    success_report
    return 0
}


run "$@"
