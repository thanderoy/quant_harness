#!/bin/bash
set -euo pipefail

# Source common variables and functions
source /scripts/02-common.sh

log_message "INFO" "------------------------------------------------"
log_message "INFO" "Running installation scripts..."

# Run installation scripts
/scripts/03-install-mono.sh
/scripts/04-install-gecko.sh
/scripts/05-install-winetricks.sh
/scripts/06-install-mt5.sh
/scripts/07-install-python.sh
/scripts/08-install-libraries.sh

# Start servers
/scripts/09-start-wine-flask.sh

# Keep the script running
tail -f /dev/null