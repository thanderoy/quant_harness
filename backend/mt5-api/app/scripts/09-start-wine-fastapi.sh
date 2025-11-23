#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "09-start-wine-fastapi.sh"

log_message "INFO" "Starting FastAPI server in Wine environment..."

# Run the FastAPI app using Wine's Python
$wine_executable python /app/main.py &

FASTAPI_PID=$!

# Give the server some time to start
sleep 5

# Check if the FastAPI server is running
if ps -p $FASTAPI_PID > /dev/null; then
    log_message "INFO" "FastAPI server in Wine started successfully with PID $FASTAPI_PID."
else
    log_message "ERROR" "Failed to start FastAPI server in Wine."
    exit 1
fi
