#!/usr/bin/env bash
set -u
set -o pipefail


# Stage10-B4 deployment is intentionally separate from the report-only
# deployment.  The production defaults below are exact; the environment
# overrides are only useful for an isolated test harness.
EXPECTED_HEAD="66b13b6bbf9e930e73e7fdff9960581ab7b30a88"

SOURCE_ROOT=${TEDDY_STAGE10_SOURCE_ROOT:-/opt/missav-pwa-holdings-stage10}
PRODUCTION_ROOT=${TEDDY_STAGE10_B4_PRODUCTION_ROOT:-/opt/missav-dlp-web}
RUNTIME_DIR="$PRODUCTION_ROOT/stage9-runtime"
DISCOVERY_DB="$PRODUCTION_ROOT/discovery/teddy-discovery.sqlite3"
BACKUP_ROOT="$PRODUCTION_ROOT/backups"

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
APPLY_TIMER_NAME="teddy-discovery-jav-reconcile-apply.timer"

CANONICAL_LIBRARY_ROOT="/volume1/video/video2/JAV"

RUNTIME_UPDATE_FILES=(
    "teddy_discovery_jav_reconcile.py"
    "teddy_discovery_organizer_apply.py"
)

RUNTIME_ADD_FILES=(
    "teddy_discovery_jav_reconcile_apply.py"
)

# These are already supplied by the Stage9/B3 runtime.  They are checked and
# included in the provenance manifest, but are never overwritten by B4.
RUNTIME_DEPENDENCY_FILES=(
    "teddy_discovery_completion_ssh.py"
    "teddy_discovery_ids.py"
    "teddy_discovery_import.py"
    "teddy_discovery_media_publish.py"
    "teddy_discovery_organizer.py"
    "teddy_discovery_operation_lock.py"
    "teddy_discovery_db.py"
)

BACKUP_DIR="UNAVAILABLE"
FAILURE_POINT="UNKNOWN"
HEAD=""
CANARY_FILESYSTEM_COUNT="UNKNOWN"
CANARY_DB_PRESENT_COUNT="UNKNOWN"
CANARY_APPLY="UNKNOWN"
CANARY_RESULT="UNKNOWN"
CANARY_ACTION="UNKNOWN"

STAGE9_TIMER_ENABLED_BEFORE="UNKNOWN"
STAGE9_TIMER_ACTIVE_BEFORE="UNKNOWN"
STAGE9_SERVICE_ACTIVE_BEFORE="UNKNOWN"
REPORT_TIMER_ENABLED_BEFORE="UNKNOWN"
REPORT_TIMER_ACTIVE_BEFORE="UNKNOWN"
REPORT_SERVICE_ACTIVE_BEFORE="UNKNOWN"

STAGE9_TIMER_ACTIVE_AFTER="UNKNOWN"
REPORT_TIMER_ACTIVE_AFTER="UNKNOWN"
STAGE9_TIMER_ENABLED_AFTER="UNKNOWN"
REPORT_TIMER_ENABLED_AFTER="UNKNOWN"

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
    printf '%s\n' "BACKUP_DIR=$BACKUP_DIR"
    printf '%s\n' "STAGE9_TIMER_ENABLED_BEFORE=$STAGE9_TIMER_ENABLED_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ENABLED_AFTER=$STAGE9_TIMER_ENABLED_AFTER"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_BEFORE=$STAGE9_TIMER_ACTIVE_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_AFTER=$STAGE9_TIMER_ACTIVE_AFTER"
    printf '%s\n' "REPORT_TIMER_ENABLED_BEFORE=$REPORT_TIMER_ENABLED_BEFORE"
    printf '%s\n' "REPORT_TIMER_ENABLED_AFTER=$REPORT_TIMER_ENABLED_AFTER"
    printf '%s\n' "REPORT_TIMER_ACTIVE_BEFORE=$REPORT_TIMER_ACTIVE_BEFORE"
    printf '%s\n' "REPORT_TIMER_ACTIVE_AFTER=$REPORT_TIMER_ACTIVE_AFTER"
    printf '%s\n' "APPLY_TIMER=ABSENT_EXPECTED"
    printf '%s\n' "TIMER_CLEANUP=$CLEANUP_STATUS"
    printf '%s\n' "AUTO_APPLY_ENABLED=NO"
}


success_report()
{
    printf '%s\n' "RESULT=PASS"
    printf '%s\n' "BACKUP_DIR=$BACKUP_DIR"
    printf '%s\n' "STAGE9_TIMER_ENABLED_BEFORE=$STAGE9_TIMER_ENABLED_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ENABLED_AFTER=$STAGE9_TIMER_ENABLED_AFTER"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_BEFORE=$STAGE9_TIMER_ACTIVE_BEFORE"
    printf '%s\n' "STAGE9_TIMER_ACTIVE_AFTER=$STAGE9_TIMER_ACTIVE_AFTER"
    printf '%s\n' "REPORT_TIMER_ENABLED_BEFORE=$REPORT_TIMER_ENABLED_BEFORE"
    printf '%s\n' "REPORT_TIMER_ENABLED_AFTER=$REPORT_TIMER_ENABLED_AFTER"
    printf '%s\n' "REPORT_TIMER_ACTIVE_BEFORE=$REPORT_TIMER_ACTIVE_BEFORE"
    printf '%s\n' "REPORT_TIMER_ACTIVE_AFTER=$REPORT_TIMER_ACTIVE_AFTER"
    printf '%s\n' "APPLY_TIMER=ABSENT"
    printf '%s\n' "APPLY_SERVICE_INSTALLED=YES"
    printf '%s\n' "CANARY_RESULT=$CANARY_RESULT"
    printf '%s\n' "CANARY_ACTION=$CANARY_ACTION"
    printf '%s\n' "APPLY=$CANARY_APPLY"
    printf '%s\n' "FILESYSTEM_COUNT=$CANARY_FILESYSTEM_COUNT"
    printf '%s\n' "DB_PRESENT_COUNT=$CANARY_DB_PRESENT_COUNT"
    printf '%s\n' "DB_SEMANTIC_UNCHANGED=PASS"
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


valid_sha256()
{
    printf '%s\n' "$1" | grep -Eq '^[0-9a-f]{64}$'
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


read_env_value()
{
    local name=$1
    awk -F= -v wanted="$name" '
        $1 == wanted {
            count++
            value = substr($0, index($0, "=") + 1)
        }
        END {
            if (count != 1 || value == "") exit 1
            print value
        }
    ' "$ENV_FILE"
}


verify_environment_file()
{
    local value

    verify_metadata "$ENV_FILE" 0600 || return 1

    for name in \
        TEDDY_FINAL_SSH_HOST \
        TEDDY_FINAL_SSH_USER \
        TEDDY_FINAL_SSH_KEY \
        TEDDY_FINAL_SSH_KNOWN_HOSTS; do
        value=$(read_env_value "$name") || return 1
        case "$value" in
            *$'\n'*|*$'\r'*) return 1 ;;
        esac
    done

    SSH_HOST=$(read_env_value TEDDY_FINAL_SSH_HOST) || return 1
    SSH_USER=$(read_env_value TEDDY_FINAL_SSH_USER) || return 1
    SSH_KEY=$(read_env_value TEDDY_FINAL_SSH_KEY) || return 1
    SSH_KNOWN_HOSTS=$(read_env_value TEDDY_FINAL_SSH_KNOWN_HOSTS) || return 1
    [ -f "$SSH_KEY" ] && [ ! -L "$SSH_KEY" ] || return 1
    [ -f "$SSH_KNOWN_HOSTS" ] && [ ! -L "$SSH_KNOWN_HOSTS" ] || return 1
    return 0
}


allowed_source_worktree_status()
{
    awk '
        $0 == "?? deploy/stage10-b4/deployment-tooling-smoke.py" ||
        $0 == "?? deploy/stage10-b4/install-stage10-b4-apply-service.sh" ||
        $0 == "?? deploy/stage10-b4/rollback-stage10-b4-apply-service.sh" {
            next
        }
        { unexpected = 1 }
        END { print (unexpected ? "FAIL" : "PASS") }
    '
}


backup_file()
{
    local source_path=$1
    local backup_path=$2

    require_regular "$source_path" "BACKUP_SOURCE_NOT_REGULAR" || return 1
    [ ! -e "$backup_path" ] || return 1
    mkdir -p "$(dirname -- "$backup_path")" || return 1
    cp -a -- "$source_path" "$backup_path" || return 1
    return 0
}


record_environment_metadata()
{
    local output=$1
    local stat_value
    local hash_value

    stat_value=$(stat -c '%u:%g:%a:%s' "$ENV_FILE") || return 1
    hash_value=$(sha256_file "$ENV_FILE") || return 1
    valid_sha256 "$hash_value" || return 1
    {
        printf 'present=1\n'
        printf 'stat=%s\n' "$stat_value"
        printf 'sha256=%s\n' "$hash_value"
    } >"$output"
}


record_source_manifest()
{
    {
        printf 'HEAD=%s\n' "$HEAD"
        for file in \
            "${RUNTIME_UPDATE_FILES[@]}" \
            "${RUNTIME_ADD_FILES[@]}" \
            "${RUNTIME_DEPENDENCY_FILES[@]}"; do
            sha256sum "$SOURCE_ROOT/$file"
        done
        sha256sum \
            "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-apply" \
            "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-apply.service" \
            "$SOURCE_ROOT/deploy/stage10-b4/separate-apply-deployment-manifest.md" \
            "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-report" \
            "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile.service" \
            "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile.timer"
    } >"$BACKUP_DIR/source-sha256.txt"
}


atomic_install()
{
    local source_path=$1
    local target_path=$2
    local mode=$3
    local temp_path="${target_path}.stage10-b4.$$"
    local source_hash
    local temp_hash

    rm -f -- "$temp_path"
    install -o root -g root -m "$mode" -- "$source_path" "$temp_path" || {
        rm -f -- "$temp_path"
        return 1
    }

    source_hash=$(sha256_file "$source_path") || {
        rm -f -- "$temp_path"
        return 1
    }
    temp_hash=$(sha256_file "$temp_path") || {
        rm -f -- "$temp_path"
        return 1
    }
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


install_provenance_marker()
{
    local temp_path="${STAGE10_B4_MARKER}.stage10-b4.$$"

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
    mv -n -- "$temp_path" "$STAGE10_B4_MARKER" || {
        rm -f -- "$temp_path"
        return 1
    }
    rm -f -- "$temp_path"
    return 0
}


verify_provenance_marker()
{
    require_regular "$STAGE10_B4_MARKER" "STAGE10_B4_MARKER_NOT_REGULAR" || return 1
    verify_metadata "$STAGE10_B4_MARKER" 0644 || return 1
    [ "$(stat -c '%s' "$STAGE10_B4_MARKER")" = "41" ] || return 1
    [ "$(cat "$STAGE10_B4_MARKER")" = "$EXPECTED_HEAD" ]
}


db_semantic_probe()
{
    local db_path=$1
    local snapshot_path=$2
    local output_path=$3

    rm -f -- "$snapshot_path"
    python3 - "$db_path" "$snapshot_path" >"$output_path" <<'PY'
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys


source_path, snapshot_path = sys.argv[1:]
source_uri = "file:" + source_path + "?mode=ro"

source = sqlite3.connect(source_uri, uri=True)
try:
    source.execute("PRAGMA query_only=ON")
    integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError("source integrity_check failed")

    destination = sqlite3.connect(snapshot_path)
    try:
        source.backup(destination)
        destination.commit()
        destination_integrity = destination.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        if destination_integrity != "ok":
            raise RuntimeError("snapshot integrity_check failed")

        def quote(identifier):
            return '"' + identifier.replace('"', '""') + '"'

        tables = [
            row[0]
            for row in destination.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        semantic = {}
        present_count = None

        for table in tables:
            columns = [
                row[1]
                for row in destination.execute(
                    "PRAGMA table_info(" + quote(table) + ")"
                )
            ]
            try:
                rows = destination.execute(
                    "SELECT * FROM " + quote(table) + " ORDER BY rowid"
                ).fetchall()
            except sqlite3.Error:
                rows = destination.execute(
                    "SELECT * FROM " + quote(table)
                ).fetchall()
                rows.sort(key=lambda row: repr(row))
            semantic[table] = {
                "columns": columns,
                "rows": rows,
            }

            if table == "holdings":
                present_index = columns.index("present")
                present_count = sum(
                    int(row[present_index] or 0) == 1
                    for row in rows
                )

        def json_value(value):
            if isinstance(value, bytes):
                return {"__bytes__": value.hex()}
            return value

        normalized = json.loads(
            json.dumps(
                semantic,
                default=json_value,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        digest = hashlib.sha256(
            json.dumps(
                normalized,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        if present_count is None:
            raise RuntimeError("holdings table missing")
        print("INTEGRITY_CHECK=ok")
        print("SEMANTIC_SHA256=" + digest)
        print("PRESENT_COUNT=" + str(present_count))
        print("TOTAL_CHANGES=" + str(source.total_changes))
    finally:
        destination.close()
finally:
    source.close()
PY
}


probe_report_only()
{
    local output_path=$1
    local rc

    PYTHONPATH="$RUNTIME_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        TEDDY_DISCOVERY_DB="$DISCOVERY_DB" \
        TEDDY_FINAL_LIBRARY_ROOT="$CANONICAL_LIBRARY_ROOT" \
        TEDDY_FINAL_SSH_HOST="$SSH_HOST" \
        TEDDY_FINAL_SSH_USER="$SSH_USER" \
        TEDDY_FINAL_SSH_KEY="$SSH_KEY" \
        TEDDY_FINAL_SSH_KNOWN_HOSTS="$SSH_KNOWN_HOSTS" \
        python3 -c '
from teddy_discovery_jav_reconcile_report import run_report
raise SystemExit(0 if run_report() == "PASS" else 1)
' >"$output_path" 2>&1
    rc=$?
    return "$rc"
}


report_probe_contract()
{
    local report_path=$1
    local count

    count=$(awk -F= '$1 == "RESULT" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$report_path") || return 1
    [ "$count" = "PASS" ] || return 1
    count=$(awk -F= '$1 == "SCAN_COMPLETE" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$report_path") || return 1
    [ "$count" = "1" ] || return 1
    count=$(awk -F= '$1 == "ROOT_AVAILABLE" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$report_path") || return 1
    [ "$count" = "1" ] || return 1
    count=$(awk -F= '$1 == "DB_AVAILABLE" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$report_path") || return 1
    [ "$count" = "1" ] || return 1
    count=$(awk -F= '$1 == "FINDING_TOTAL" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$report_path") || return 1
    [ "$count" = "0" ] || return 1
    count=$(awk -F= '$1 == "APPLY" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$report_path") || return 1
    [ "$count" = "0" ] || return 1

    CANARY_FILESYSTEM_COUNT=$(awk -F= '$1 == "FILESYSTEM_COUNT" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$report_path") || return 1
    CANARY_DB_PRESENT_COUNT=$(awk -F= '$1 == "DB_PRESENT_COUNT" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$report_path") || return 1
    [ -n "$CANARY_FILESYSTEM_COUNT" ] || return 1
    [ "$CANARY_FILESYSTEM_COUNT" = "$CANARY_DB_PRESENT_COUNT" ] || return 1
    return 0
}


parse_noop_canary_journal()
{
    local journal_path=$1
    local value

    value=$(awk -F= '$1 == "RESULT" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$journal_path") || return 1
    [ "$value" = "PASS" ] || return 1
    CANARY_RESULT=$value
    value=$(awk -F= '$1 == "ACTION" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$journal_path") || return 1
    [ "$value" = "NOOP" ] || return 1
    CANARY_ACTION=$value
    value=$(awk -F= '$1 == "APPLY" { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$journal_path") || return 1
    [ "$value" = "0" ] || return 1
    CANARY_APPLY=$value
    for key in INSERTED ABSENT_MARKED REVIVED METADATA_UPDATED; do
        value=$(awk -F= -v wanted="$key" '$1 == wanted { n++; value=$2 } END { if (n == 1) print value; else exit 1 }' "$journal_path") || return 1
        [ "$value" = "0" ] || return 1
    done
    return 0
}


stop_timer_if_active()
{
    local timer_name=$1
    local state=$2

    [ "$state" = "active" ] || return 0
    systemctl stop "$timer_name" >/dev/null 2>&1 || return 1
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
    STAGE9_TIMER_ENABLED_AFTER=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    REPORT_TIMER_ENABLED_AFTER=$(unit_state is-enabled "$REPORT_TIMER_NAME")
    if [ "$CLEANUP_OUTPUT" -eq 1 ] && [ "$rc" -ne 0 ]; then
        printf '%s\n' "TIMER_CLEANUP=FAIL"
        printf '%s\n' "HIGH_PRIORITY=TIMER_STATE_RESTORE_FAILED"
    fi
    return "$rc"
}


precheck()
{
    local worktree_status
    local units
    local state
    local rc

    [ "$(id -u)" -eq 0 ] || { fail_at "ROOT_REQUIRED"; return 1; }

    for command_name in \
        git systemctl systemd-analyze install mv rm cp sha256sum awk python3 \
        bash sh journalctl date grep mkdir chown chmod stat sleep id cat; do
        require_command "$command_name" || return 1
    done

    [ -d "$SOURCE_ROOT/.git" ] || [ -f "$SOURCE_ROOT/.git" ] || {
        fail_at "SOURCE_ROOT_NOT_GIT_WORKTREE"
        return 1
    }
    HEAD=$(git -C "$SOURCE_ROOT" rev-parse HEAD 2>/dev/null) || {
        fail_at "SOURCE_HEAD_UNREADABLE"
        return 1
    }
    [ "$HEAD" = "$EXPECTED_HEAD" ] || { fail_at "SOURCE_HEAD_MISMATCH"; return 1; }

    worktree_status=$(git -C "$SOURCE_ROOT" status --porcelain=v1 --untracked-files=all 2>/dev/null) || {
        fail_at "SOURCE_WORKTREE_STATUS_UNREADABLE"
        return 1
    }
    if [ -n "$worktree_status" ] && \
        [ "$(printf '%s\n' "$worktree_status" | allowed_source_worktree_status)" != "PASS" ]; then
        fail_at "SOURCE_WORKTREE_NOT_CLEAN"
        return 1
    fi

    for file in \
        "${RUNTIME_UPDATE_FILES[@]}" \
        "${RUNTIME_ADD_FILES[@]}" \
        "${RUNTIME_DEPENDENCY_FILES[@]}"; do
        require_regular "$SOURCE_ROOT/$file" "SOURCE_MISSING_$file" || return 1
    done
    for file in \
        deploy/systemd/teddy-discovery-jav-reconcile-apply \
        deploy/systemd/teddy-discovery-jav-reconcile-apply.service \
        deploy/stage10-b4/separate-apply-deployment-manifest.md \
        deploy/systemd/teddy-discovery-jav-reconcile-report \
        deploy/systemd/teddy-discovery-jav-reconcile.service \
        deploy/systemd/teddy-discovery-jav-reconcile.timer; do
        require_regular "$SOURCE_ROOT/$file" "SOURCE_DEPLOYMENT_MISSING_$file" || return 1
    done

    require_regular "$RUNTIME_DIR/teddy_discovery_jav_reconcile.py" "PRODUCTION_RUNTIME_RECONCILE_MISSING" || return 1
    require_regular "$RUNTIME_DIR/teddy_discovery_organizer_apply.py" "PRODUCTION_RUNTIME_ORGANIZER_APPLY_MISSING" || return 1
    for file in "${RUNTIME_DEPENDENCY_FILES[@]}"; do
        require_regular "$RUNTIME_DIR/$file" "PRODUCTION_RUNTIME_DEPENDENCY_MISSING_$file" || return 1
    done
    if [ ! -f "$STAGE9_MARKER" ] || [ -L "$STAGE9_MARKER" ]; then
        fail_at "PRODUCTION_STAGE9_MARKER_MISSING"
        return 1
    fi
    require_regular "$STAGE10_B3_MARKER" "PRODUCTION_STAGE10_B3_MARKER_MISSING" || return 1
    require_absent "$STAGE10_B4_MARKER" "PRODUCTION_STAGE10_B4_MARKER_ALREADY_EXISTS" || return 1

    verify_environment_file || { fail_at "ENVIRONMENT_FILE_INVALID"; return 1; }
    require_regular "$DISCOVERY_DB" "PRODUCTION_DB_MISSING" || return 1

    for path in "$STAGE9_WRAPPER" "$STAGE9_SERVICE" "$STAGE9_TIMER" \
        "$REPORT_WRAPPER" "$REPORT_SERVICE" "$REPORT_TIMER"; do
        require_regular "$path" "PRODUCTION_REQUIRED_ARTIFACT_MISSING_$path" || return 1
    done

    grep -Fq "ExecStart=$STAGE9_WRAPPER" "$STAGE9_SERVICE" || { fail_at "STAGE9_SERVICE_MISMATCH"; return 1; }
    grep -Fq "ExecStart=$REPORT_WRAPPER" "$REPORT_SERVICE" || { fail_at "REPORT_SERVICE_MISMATCH"; return 1; }
    grep -Fq "TEDDY_FINAL_LIBRARY_ROOT=$CANONICAL_LIBRARY_ROOT" "$REPORT_SERVICE" || { fail_at "REPORT_ROOT_MISMATCH"; return 1; }

    for path in "$RUNTIME_DIR/teddy_discovery_jav_reconcile_apply.py" "$APPLY_WRAPPER" "$APPLY_SERVICE" "$APPLY_TIMER" "$APPLY_SERVICE_DROPIN"; do
        require_absent "$path" "APPLY_ARTIFACT_ALREADY_EXISTS_$path" || return 1
    done
    unit_files=$(systemctl list-unit-files --no-legend --no-pager 2>/dev/null)
    rc=$?
    if [ "$rc" -ne 0 ]; then
        fail_at "APPLY_UNIT_STATE_UNREADABLE"
        return 1
    fi

    units=$(printf '%s\n' "$unit_files" | awk '$1 ~ /^teddy-discovery-jav-reconcile-apply/ { print }')
    if [ -n "$units" ]; then
        fail_at "UNEXPECTED_APPLY_UNIT_EXISTS"
        return 1
    fi

    STAGE9_TIMER_ENABLED_BEFORE=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    REPORT_TIMER_ENABLED_BEFORE=$(unit_state is-enabled "$REPORT_TIMER_NAME")
    STAGE9_TIMER_ACTIVE_BEFORE=$(unit_state is-active "$STAGE9_TIMER_NAME")
    REPORT_TIMER_ACTIVE_BEFORE=$(unit_state is-active "$REPORT_TIMER_NAME")
    STAGE9_SERVICE_ACTIVE_BEFORE=$(unit_state is-active "$STAGE9_SERVICE_NAME")
    REPORT_SERVICE_ACTIVE_BEFORE=$(unit_state is-active "$REPORT_SERVICE_NAME")

    valid_enabled_state "$STAGE9_TIMER_ENABLED_BEFORE" || { fail_at "STAGE9_TIMER_ENABLED_STATE_INVALID"; return 1; }
    valid_enabled_state "$REPORT_TIMER_ENABLED_BEFORE" || { fail_at "REPORT_TIMER_ENABLED_STATE_INVALID"; return 1; }
    [ "$STAGE9_TIMER_ENABLED_BEFORE" = "enabled" ] || [ "$STAGE9_TIMER_ENABLED_BEFORE" = "enabled-runtime" ] || { fail_at "STAGE9_TIMER_NOT_ENABLED"; return 1; }
    [ "$REPORT_TIMER_ENABLED_BEFORE" = "enabled" ] || [ "$REPORT_TIMER_ENABLED_BEFORE" = "enabled-runtime" ] || { fail_at "REPORT_TIMER_NOT_ENABLED"; return 1; }
    valid_active_state "$STAGE9_TIMER_ACTIVE_BEFORE" || { fail_at "STAGE9_TIMER_ACTIVE_STATE_INVALID"; return 1; }
    valid_active_state "$REPORT_TIMER_ACTIVE_BEFORE" || { fail_at "REPORT_TIMER_ACTIVE_STATE_INVALID"; return 1; }
    valid_active_state "$STAGE9_SERVICE_ACTIVE_BEFORE" || { fail_at "STAGE9_SERVICE_ACTIVE_STATE_INVALID"; return 1; }
    valid_active_state "$REPORT_SERVICE_ACTIVE_BEFORE" || { fail_at "REPORT_SERVICE_ACTIVE_STATE_INVALID"; return 1; }
    [ "$STAGE9_TIMER_ACTIVE_BEFORE" = "active" ] || { fail_at "STAGE9_TIMER_NOT_ACTIVE"; return 1; }
    [ "$REPORT_TIMER_ACTIVE_BEFORE" = "active" ] || { fail_at "REPORT_TIMER_NOT_ACTIVE"; return 1; }

    return 0
}


write_pre_state()
{
    local env_stat env_hash

    env_stat=$(stat -c '%u:%g:%a:%s' "$ENV_FILE") || return 1
    env_hash=$(sha256_file "$ENV_FILE") || return 1
    {
        printf 'source_root=%s\n' "$SOURCE_ROOT"
        printf 'source_head=%s\n' "$HEAD"
        printf 'stage9_timer_enabled_before=%s\n' "$STAGE9_TIMER_ENABLED_BEFORE"
        printf 'stage9_timer_active_before=%s\n' "$STAGE9_TIMER_ACTIVE_BEFORE"
        printf 'stage9_service_active_before=%s\n' "$STAGE9_SERVICE_ACTIVE_BEFORE"
        printf 'report_timer_enabled_before=%s\n' "$REPORT_TIMER_ENABLED_BEFORE"
        printf 'report_timer_active_before=%s\n' "$REPORT_TIMER_ACTIVE_BEFORE"
        printf 'report_service_active_before=%s\n' "$REPORT_SERVICE_ACTIVE_BEFORE"
        printf 'stage9_marker_sha256=%s\n' "$(sha256_file "$STAGE9_MARKER")"
        printf 'stage10_b3_marker_sha256=%s\n' "$(sha256_file "$STAGE10_B3_MARKER")"
        printf 'environment_file_stat=%s\n' "$env_stat"
        printf 'environment_file_sha256=%s\n' "$env_hash"
        printf 'stage9_wrapper_sha256=%s\n' "$(sha256_file "$STAGE9_WRAPPER")"
        printf 'stage9_service_sha256=%s\n' "$(sha256_file "$STAGE9_SERVICE")"
        printf 'stage9_timer_sha256=%s\n' "$(sha256_file "$STAGE9_TIMER")"
        printf 'report_wrapper_sha256=%s\n' "$(sha256_file "$REPORT_WRAPPER")"
        printf 'report_service_sha256=%s\n' "$(sha256_file "$REPORT_SERVICE")"
        printf 'report_timer_sha256=%s\n' "$(sha256_file "$REPORT_TIMER")"
        printf 'apply_timer=ABSENT\n'
        printf 'canary=ONE_APPLY_SERVICE_START\n'
    } >"$BACKUP_DIR/pre-state.txt"
}


quiesce()
{
    if [ "$STAGE9_TIMER_ACTIVE_BEFORE" = "active" ]; then
        STAGE9_TIMER_STOP_ATTEMPTED=1
        stop_timer_if_active "$STAGE9_TIMER_NAME" active || { fail_at "STAGE9_TIMER_STOP_FAILED"; return 1; }
    fi
    if [ "$REPORT_TIMER_ACTIVE_BEFORE" = "active" ]; then
        REPORT_TIMER_STOP_ATTEMPTED=1
        stop_timer_if_active "$REPORT_TIMER_NAME" active || { fail_at "REPORT_TIMER_STOP_FAILED"; return 1; }
    fi
    wait_service_quiesced "$STAGE9_SERVICE_NAME" STAGE9 || return 1
    wait_service_quiesced "$REPORT_SERVICE_NAME" REPORT || return 1
    return 0
}


verify_report_unchanged()
{
    local before after path name
    for pair in \
        "$REPORT_WRAPPER:report_wrapper_sha256" \
        "$REPORT_SERVICE:report_service_sha256" \
        "$REPORT_TIMER:report_timer_sha256" \
        "$STAGE9_WRAPPER:stage9_wrapper_sha256" \
        "$STAGE9_SERVICE:stage9_service_sha256" \
        "$STAGE9_TIMER:stage9_timer_sha256"; do
        path=${pair%%:*}
        name=${pair##*:}
        before=$(awk -F= -v wanted="$name" '$1 == wanted { print $2 }' "$BACKUP_DIR/pre-state.txt")
        after=$(sha256_file "$path") || return 1
        [ -n "$before" ] && [ "$before" = "$after" ] || return 1
    done
    return 0
}


verify_installed_artifacts()
{
    local source_path target_path mode

    for file in "${RUNTIME_UPDATE_FILES[@]}"; do
        source_path="$SOURCE_ROOT/$file"
        target_path="$RUNTIME_DIR/$file"
        verify_metadata "$target_path" 0644 || return 1
        [ "$(sha256_file "$source_path")" = "$(sha256_file "$target_path")" ] || return 1
    done
    for file in "${RUNTIME_ADD_FILES[@]}"; do
        source_path="$SOURCE_ROOT/$file"
        target_path="$RUNTIME_DIR/$file"
        verify_metadata "$target_path" 0644 || return 1
        [ "$(sha256_file "$source_path")" = "$(sha256_file "$target_path")" ] || return 1
    done

    verify_metadata "$APPLY_WRAPPER" 0755 || return 1
    verify_metadata "$APPLY_SERVICE" 0644 || return 1
    [ "$(sha256_file "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-apply")" = "$(sha256_file "$APPLY_WRAPPER")" ] || return 1
    [ "$(sha256_file "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-apply.service")" = "$(sha256_file "$APPLY_SERVICE")" ] || return 1
    grep -Fq 'Type=oneshot' "$APPLY_SERVICE" || return 1
    grep -Fq 'EnvironmentFile=-/etc/default/teddy-discovery' "$APPLY_SERVICE" || return 1
    grep -Fq "Environment=TEDDY_DISCOVERY_RUNTIME=$RUNTIME_DIR" "$APPLY_SERVICE" || return 1
    grep -Fq "Environment=TEDDY_DISCOVERY_DB=$DISCOVERY_DB" "$APPLY_SERVICE" || return 1
    grep -Fq "Environment=TEDDY_FINAL_LIBRARY_ROOT=$CANONICAL_LIBRARY_ROOT" "$APPLY_SERVICE" || return 1
    grep -Fq "ExecStart=$APPLY_WRAPPER" "$APPLY_SERVICE" || return 1
    ! grep -Eq '^Restart=' "$APPLY_SERVICE" || return 1
    require_absent "$APPLY_TIMER" "APPLY_TIMER_CREATED" || return 1
    return 0
}


install_runtime()
{
    for file in "${RUNTIME_UPDATE_FILES[@]}"; do
        atomic_install "$SOURCE_ROOT/$file" "$RUNTIME_DIR/$file" 0644 || {
            fail_at "RUNTIME_UPDATE_FAILED_$file"
            return 1
        }
    done
    for file in "${RUNTIME_ADD_FILES[@]}"; do
        atomic_install "$SOURCE_ROOT/$file" "$RUNTIME_DIR/$file" 0644 || {
            fail_at "RUNTIME_ADD_FAILED_$file"
            return 1
        }
    done
    atomic_install "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-apply" "$APPLY_WRAPPER" 0755 || {
        fail_at "APPLY_WRAPPER_INSTALL_FAILED"
        return 1
    }
    atomic_install "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-apply.service" "$APPLY_SERVICE" 0644 || {
        fail_at "APPLY_SERVICE_INSTALL_FAILED"
        return 1
    }
    return 0
}


run_manual_noop_canary()
{
    local db_before="$BACKUP_DIR/canary-db-before.sqlite3"
    local db_after="$BACKUP_DIR/canary-db-after.sqlite3"
    local before_probe="$BACKUP_DIR/canary-db-before.txt"
    local after_probe="$BACKUP_DIR/canary-db-after.txt"
    local pre_report="$BACKUP_DIR/canary-preflight-report.txt"
    local post_report="$BACKUP_DIR/canary-postflight-report.txt"
    local canary_journal="$BACKUP_DIR/canary-apply-journal.txt"
    local journal_cursor
    local before_semantic after_semantic before_count after_count
    local baseline_filesystem_count baseline_db_present_count
    local start_rc journal_rc

    # This is a read-only report probe.  It supplies the actual counts for the
    # canary output without hard-coding 148 and verifies the coherent baseline.
    probe_report_only "$pre_report" || { fail_at "CANARY_PREFLIGHT_REPORT_FAILED"; return 1; }
    report_probe_contract "$pre_report" || { fail_at "CANARY_PREFLIGHT_REPORT_UNSAFE"; return 1; }
    baseline_filesystem_count=$CANARY_FILESYSTEM_COUNT
    baseline_db_present_count=$CANARY_DB_PRESENT_COUNT

    db_semantic_probe "$DISCOVERY_DB" "$db_before" "$before_probe" || {
        fail_at "CANARY_DB_BEFORE_PROBE_FAILED"
        return 1
    }
    before_semantic=$(awk -F= '$1 == "SEMANTIC_SHA256" { print $2 }' "$before_probe")
    before_count=$(awk -F= '$1 == "PRESENT_COUNT" { print $2 }' "$before_probe")
    [ -n "$before_semantic" ] && [ "$before_count" = "$CANARY_DB_PRESENT_COUNT" ] || {
        fail_at "CANARY_DB_PREFLIGHT_COUNT_MISMATCH"
        return 1
    }

    journal_cursor=$(
        journalctl \
            --no-pager \
            --quiet \
            --lines=1 \
            --show-cursor \
            2>/dev/null \
        | sed -n 's/^-- cursor: //p' \
        | tail -n 1
    )
    [ -n "$journal_cursor" ] || {
        fail_at "CANARY_JOURNAL_CURSOR_UNAVAILABLE"
        return 1
    }

    systemctl start "$APPLY_SERVICE_NAME" >/dev/null 2>&1
    start_rc=$?

    journalctl \
        --unit="$APPLY_SERVICE_NAME" \
        --after-cursor="$journal_cursor" \
        --no-pager \
        --output=cat \
        >"$canary_journal" 2>&1
    journal_rc=$?

    if [ "$start_rc" -ne 0 ] || [ "$journal_rc" -ne 0 ]; then
        fail_at "CANARY_APPLY_SERVICE_START_OR_JOURNAL_FAILED"
        return 1
    fi
    parse_noop_canary_journal "$canary_journal" || {
        fail_at "CANARY_NOT_EXACT_NOOP"
        return 1
    }

    db_semantic_probe "$DISCOVERY_DB" "$db_after" "$after_probe" || {
        fail_at "CANARY_DB_AFTER_PROBE_FAILED"
        return 1
    }
    after_semantic=$(awk -F= '$1 == "SEMANTIC_SHA256" { print $2 }' "$after_probe")
    after_count=$(awk -F= '$1 == "PRESENT_COUNT" { print $2 }' "$after_probe")
    [ "$before_semantic" = "$after_semantic" ] || { fail_at "CANARY_DB_SEMANTIC_CHANGED"; return 1; }
    [ "$before_count" = "$after_count" ] || { fail_at "CANARY_DB_PRESENT_COUNT_CHANGED"; return 1; }
    grep -Fxq 'INTEGRITY_CHECK=ok' "$after_probe" || { fail_at "CANARY_DB_INTEGRITY_FAILED"; return 1; }
    grep -Fxq 'TOTAL_CHANGES=0' "$after_probe" || { fail_at "CANARY_DB_READ_ONLY_CHANGES_DETECTED"; return 1; }

    probe_report_only "$post_report" || { fail_at "CANARY_POSTFLIGHT_REPORT_FAILED"; return 1; }
    report_probe_contract "$post_report" || { fail_at "CANARY_POSTFLIGHT_REPORT_UNSAFE"; return 1; }
    [ "$CANARY_FILESYSTEM_COUNT" = "$baseline_filesystem_count" ] || { fail_at "CANARY_FILESYSTEM_COUNT_CHANGED"; return 1; }
    [ "$CANARY_DB_PRESENT_COUNT" = "$baseline_db_present_count" ] || { fail_at "CANARY_REPORT_DB_COUNT_CHANGED"; return 1; }
    [ "$CANARY_FILESYSTEM_COUNT" = "$CANARY_DB_PRESENT_COUNT" ] || { fail_at "CANARY_POSTFLIGHT_COUNT_MISMATCH"; return 1; }
    return 0
}


main()
{
    local file
    local state

    umask 077
    precheck || return 1

    STAMP=$(date '+%Y%m%d-%H%M%S')
    BACKUP_DIR="$BACKUP_ROOT/stage10-b4-$STAMP"
    [ ! -e "$BACKUP_DIR" ] || { fail_at "BACKUP_DIR_ALREADY_EXISTS"; return 1; }
    mkdir -p "$BACKUP_DIR/runtime" "$BACKUP_DIR/systemd" "$BACKUP_DIR/etc-default" "$BACKUP_DIR/pycache" || {
        fail_at "BACKUP_DIR_CREATE_FAILED"
        return 1
    }

    record_source_manifest || { fail_at "SOURCE_HASH_MANIFEST_FAILED"; return 1; }
    for file in "${RUNTIME_UPDATE_FILES[@]}"; do
        backup_file "$RUNTIME_DIR/$file" "$BACKUP_DIR/runtime/$file" || {
            fail_at "BACKUP_RUNTIME_FAILED_$file"
            return 1
        }
    done
    backup_file "$STAGE9_MARKER" "$BACKUP_DIR/runtime/.teddy-stage9-commit" || { fail_at "BACKUP_STAGE9_MARKER_FAILED"; return 1; }
    backup_file "$STAGE10_B3_MARKER" "$BACKUP_DIR/runtime/.teddy-stage10-b3-commit" || { fail_at "BACKUP_STAGE10_B3_MARKER_FAILED"; return 1; }
    record_environment_metadata "$BACKUP_DIR/etc-default/teddy-discovery.metadata" || { fail_at "BACKUP_ENVIRONMENT_METADATA_FAILED"; return 1; }
    write_pre_state || { fail_at "PRE_STATE_RECORD_FAILED"; return 1; }

    quiesce || return 1
    install_runtime || return 1
    verify_installed_artifacts || { fail_at "INSTALLED_ARTIFACT_VERIFICATION_FAILED"; return 1; }
    PYTHONPYCACHEPREFIX="$BACKUP_DIR/pycache" python3 -m py_compile \
        "$RUNTIME_DIR/teddy_discovery_jav_reconcile.py" \
        "$RUNTIME_DIR/teddy_discovery_organizer_apply.py" \
        "$RUNTIME_DIR/teddy_discovery_jav_reconcile_apply.py" \
        "$RUNTIME_DIR/teddy_discovery_completion_ssh.py" \
        "$RUNTIME_DIR/teddy_discovery_ids.py" \
        "$RUNTIME_DIR/teddy_discovery_import.py" \
        "$RUNTIME_DIR/teddy_discovery_media_publish.py" \
        "$RUNTIME_DIR/teddy_discovery_organizer.py" \
        "$RUNTIME_DIR/teddy_discovery_operation_lock.py" \
        "$RUNTIME_DIR/teddy_discovery_db.py" >/dev/null 2>&1 || {
        fail_at "PYCOMPILE_FAILED"
        return 1
    }
    sh -n "$APPLY_WRAPPER" >/dev/null 2>&1 || { fail_at "APPLY_WRAPPER_SH_SYNTAX_FAILED"; return 1; }
    bash -n "$APPLY_WRAPPER" >/dev/null 2>&1 || { fail_at "APPLY_WRAPPER_BASH_SYNTAX_FAILED"; return 1; }
    systemd-analyze verify "$APPLY_SERVICE" >"$BACKUP_DIR/systemd-verify.txt" 2>&1 || {
        fail_at "APPLY_SYSTEMD_VERIFY_FAILED"
        return 1
    }
    install_provenance_marker || { fail_at "STAGE10_B4_MARKER_INSTALL_FAILED"; return 1; }
    verify_provenance_marker || { fail_at "STAGE10_B4_MARKER_VERIFY_FAILED"; return 1; }

    systemctl daemon-reload >"$BACKUP_DIR/daemon-reload.txt" 2>&1 || {
        fail_at "SYSTEMD_DAEMON_RELOAD_FAILED"
        return 1
    }
    verify_report_unchanged || { fail_at "EXISTING_REPORT_OR_STAGE9_ARTIFACT_CHANGED"; return 1; }

    # Restore only timers that were active before quiesce.  No enable/disable
    # operation is performed; the apply service has no timer at all.
    restore_active_timers || { fail_at "TIMER_ACTIVE_STATE_RESTORE_FAILED"; return 1; }
    STAGE9_TIMER_ENABLED_AFTER=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    REPORT_TIMER_ENABLED_AFTER=$(unit_state is-enabled "$REPORT_TIMER_NAME")
    [ "$STAGE9_TIMER_ENABLED_AFTER" = "$STAGE9_TIMER_ENABLED_BEFORE" ] || { fail_at "STAGE9_TIMER_ENABLED_STATE_CHANGED"; return 1; }
    [ "$REPORT_TIMER_ENABLED_AFTER" = "$REPORT_TIMER_ENABLED_BEFORE" ] || { fail_at "REPORT_TIMER_ENABLED_STATE_CHANGED"; return 1; }

    run_manual_noop_canary || return 1
    verify_report_unchanged || { fail_at "EXISTING_ARTIFACT_CHANGED_AFTER_CANARY"; return 1; }
    require_absent "$APPLY_TIMER" "APPLY_TIMER_PRESENT_AFTER_CANARY" || return 1
    STAGE9_TIMER_ENABLED_AFTER=$(unit_state is-enabled "$STAGE9_TIMER_NAME")
    REPORT_TIMER_ENABLED_AFTER=$(unit_state is-enabled "$REPORT_TIMER_NAME")
    STAGE9_TIMER_ACTIVE_AFTER=$(unit_state is-active "$STAGE9_TIMER_NAME")
    REPORT_TIMER_ACTIVE_AFTER=$(unit_state is-active "$REPORT_TIMER_NAME")
    [ "$STAGE9_TIMER_ENABLED_AFTER" = "$STAGE9_TIMER_ENABLED_BEFORE" ] || { fail_at "STAGE9_TIMER_ENABLED_STATE_CHANGED_AFTER_CANARY"; return 1; }
    [ "$REPORT_TIMER_ENABLED_AFTER" = "$REPORT_TIMER_ENABLED_BEFORE" ] || { fail_at "REPORT_TIMER_ENABLED_STATE_CHANGED_AFTER_CANARY"; return 1; }
    [ "$STAGE9_TIMER_ACTIVE_AFTER" = "$STAGE9_TIMER_ACTIVE_BEFORE" ] || { fail_at "STAGE9_TIMER_ACTIVE_STATE_CHANGED_AFTER_CANARY"; return 1; }
    [ "$REPORT_TIMER_ACTIVE_AFTER" = "$REPORT_TIMER_ACTIVE_BEFORE" ] || { fail_at "REPORT_TIMER_ACTIVE_STATE_CHANGED_AFTER_CANARY"; return 1; }
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
