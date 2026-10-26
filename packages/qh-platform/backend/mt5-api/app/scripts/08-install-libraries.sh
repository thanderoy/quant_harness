#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "08-install-libraries.sh"

# Run every start, not only when MetaTrader5 is missing. requirements.txt holds
# floors, so this is a no-op unless something sits below one. Skipping it once
# MetaTrader5 existed is how a Wine prefix kept a library too old for the
# terminal build the server pushed (2026-10-18).
log_message "INFO" "Installing MetaTrader5 library and dependencies in Windows"
if ! $wine_executable python -m pip install --no-cache-dir -r /app/requirements.txt; then
    log_message "ERROR" "pip install -r requirements.txt failed; continuing with what is installed."
fi
