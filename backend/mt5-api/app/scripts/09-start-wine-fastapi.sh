#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "09-start-wine-fastapi.sh"

start_fastapi

# Poll the port rather than the PID. The old check ("is the wine wrapper PID
# alive 5 seconds later?") passed even when the server never bound its port.
if wait_for_api 30 10; then
    log_message "INFO" "FastAPI server in Wine is answering on port ${api_port}."
else
    log_message "ERROR" "FastAPI server did not answer on port ${api_port} within 5 minutes."
    log_message "ERROR" "Leaving recovery to 10-supervise.sh; container healthcheck will report unhealthy."
fi
