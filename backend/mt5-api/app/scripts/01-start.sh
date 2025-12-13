#!/bin/bash

# Source common variables and functions
source /scripts/02-common.sh

log_message "INFO" "------------------------------------------------"
log_message "INFO" "Running installation scripts..."

# Optional dependencies - allow failures (Mono/Gecko are nice-to-have)
/scripts/03-install-mono.sh || log_message "WARN" "Mono installation failed, continuing..."
/scripts/04-install-gecko.sh || log_message "WARN" "Gecko installation failed, continuing..."
/scripts/05-install-winetricks.sh || log_message "WARN" "Winetricks setup failed, continuing..."

# Required scripts - fail if these don't work
set -e
/scripts/06-install-mt5.sh
/scripts/07-install-python.sh
/scripts/08-install-libraries.sh

# Start FastAPI server inside Wine
/scripts/09-start-wine-fastapi.sh

log_message "INFO" "------------------------------------------------"
log_message "INFO" "Container is ready."

# Keep the script running
tail -f /dev/null
