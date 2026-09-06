#!/bin/bash
#
# Keeps the MT5 terminal and the FastAPI server alive for the life of the
# container.
#
# Why this exists: both processes are started with '&' by 06-install-mt5.sh and
# 09-start-wine-fastapi.sh, from a cont-init.d oneshot. s6 supervises PID 1 and
# the VNC/nginx services, but nothing supervises these two. On 2026-09-01 a
# large tick pull triggered a host OOM that killed the Wine process tree; s6
# stayed up, so Docker reported the container healthy-in-the-'Up'-sense and
# never restarted it. The container sat with a dead API for five days while its
# own healthcheck failed 14,425 consecutive times and nothing acted on the
# result. This loop is what acts on it.
#
# Deliberately conservative: exponential backoff up to a ceiling, and a cap on
# consecutive failed recoveries so a genuinely broken install surfaces as a
# permanently unhealthy container instead of an endless Wine restart storm.

source /scripts/02-common.sh

CHECK_INTERVAL="${MT5_SUPERVISE_INTERVAL:-60}"
BACKOFF_START="${MT5_SUPERVISE_BACKOFF_START:-30}"
BACKOFF_MAX="${MT5_SUPERVISE_BACKOFF_MAX:-600}"
MAX_CONSECUTIVE_FAILURES="${MT5_SUPERVISE_MAX_FAILURES:-10}"

log_message "RUNNING" "10-supervise.sh (interval ${CHECK_INTERVAL}s)"

consecutive_failures=0
backoff="$BACKOFF_START"
restarts=0

recover() {
    # Cheapest repair first. If the service is up and only the terminal link is
    # missing — the state both containers sat in after restarting — a single
    # connect call fixes it, with no Wine restart and no downtime.
    if api_responding; then
        log_message "WARN" "API responding but terminal link is down — calling /api/v1/connect."
        if api_connect && api_connected; then
            restarts=$((restarts + 1))
            log_message "INFO" "Reconnected without a restart (recovery #${restarts})."
            return 0
        fi
        log_message "WARN" "Reconnect did not take; falling through to a restart."
    fi

    log_message "WARN" "API unhealthy on port ${api_port} — attempting recovery."

    if ! terminal_running; then
        log_message "WARN" "MT5 terminal is not running."
        ensure_terminal || log_message "ERROR" "Failed to start MT5 terminal."
    fi

    if fastapi_running; then
        log_message "INFO" "Stopping unresponsive FastAPI process before restart."
        pkill -f "main.py" || true
        sleep 5
    fi

    start_fastapi

    # The terminal needs a moment after launch before it will accept a link.
    if wait_for_responding 18 10 && api_connect && api_connected; then
        restarts=$((restarts + 1))
        log_message "INFO" "Recovery succeeded (restart #${restarts})."
        return 0
    fi

    log_message "ERROR" "Recovery attempt did not bring the API back."
    return 1
}

while true; do
    sleep "$CHECK_INTERVAL"

    if api_healthy; then
        if [ "$consecutive_failures" -gt 0 ]; then
            log_message "INFO" "API healthy again after ${consecutive_failures} failed check(s)."
        fi
        consecutive_failures=0
        backoff="$BACKOFF_START"
        continue
    fi

    consecutive_failures=$((consecutive_failures + 1))
    log_message "WARN" "Health check failed (${consecutive_failures}/${MAX_CONSECUTIVE_FAILURES})."

    if [ "$consecutive_failures" -ge "$MAX_CONSECUTIVE_FAILURES" ]; then
        log_message "ERROR" "Giving up after ${MAX_CONSECUTIVE_FAILURES} consecutive failed recoveries."
        log_message "ERROR" "Container will remain unhealthy until manually investigated."
        # Stop trying, but stay alive so logs and VNC remain reachable for
        # diagnosis. The healthcheck keeps reporting unhealthy.
        tail -f /dev/null
    fi

    if recover; then
        consecutive_failures=0
        backoff="$BACKOFF_START"
    else
        log_message "INFO" "Backing off ${backoff}s before the next recovery attempt."
        sleep "$backoff"
        backoff=$((backoff * 2))
        if [ "$backoff" -gt "$BACKOFF_MAX" ]; then
            backoff="$BACKOFF_MAX"
        fi
    fi
done
