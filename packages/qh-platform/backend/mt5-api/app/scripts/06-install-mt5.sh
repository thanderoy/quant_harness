#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "06-install-mt5.sh"

# Check if MetaTrader 5 is installed
if [ -e "$mt5file" ]; then
    log_message "INFO" "File $mt5file already exists."
else
    log_message "INFO" "File $mt5file is not installed. Installing..."

    # Set Windows 10 mode in Wine and download and install MT5
    $wine_executable reg add "HKEY_CURRENT_USER\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f
    
    # Download MT5 with retry logic
    log_message "INFO" "Downloading MT5 installer..."
    MAX_RETRIES=3
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if wget -O /tmp/mt5setup.exe $mt5setup_url 2>&1; then
            log_message "INFO" "MT5 installer downloaded successfully."
            break
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            log_message "WARN" "Download failed. Retry $RETRY_COUNT of $MAX_RETRIES..."
            sleep $((RETRY_COUNT * 5))
        fi
    done
    
    if [ ! -f /tmp/mt5setup.exe ]; then
        log_message "ERROR" "Failed to download MT5 installer after $MAX_RETRIES attempts."
        exit 1
    fi
    
    log_message "INFO" "Installing MetaTrader 5..."
    $wine_executable /tmp/mt5setup.exe /auto
    rm -f /tmp/mt5setup.exe
fi

# Recheck if MetaTrader 5 is installed
if [ -e "$mt5file" ]; then
    log_message "INFO" "File $mt5file is installed. Running MT5..."
    $wine_executable "$mt5file" &
else
    log_message "ERROR" "File $mt5file is not installed. MT5 cannot be run."
fi