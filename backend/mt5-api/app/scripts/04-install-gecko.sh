#!/bin/bash

# Install Gecko silently to avoid Wine popups on first run
source /scripts/02-common.sh

log_message "RUNNING" "04-install-gecko.sh"

# Determine latest gecko versions known-good for stable Wine; pin versions for reproducibility
GECKO_X64_URL="https://dl.winehq.org/wine/wine-gecko/2.47.4/wine-gecko-2.47.4-x86_64.msi"
GECKO_X86_URL="https://dl.winehq.org/wine/wine-gecko/2.47.4/wine-gecko-2.47.4-x86.msi"

TMP_DIR="/tmp/wine-gecko"
mkdir -p "$TMP_DIR"

# Install x86_64 gecko if not present
if [ ! -e "/config/.wine/drive_c/windows/gecko" ]; then
    log_message "INFO" "Installing Wine Gecko (x86_64 and x86)"
    wget -O "$TMP_DIR/gecko64.msi" "$GECKO_X64_URL" > /dev/null 2>&1
    wget -O "$TMP_DIR/gecko32.msi" "$GECKO_X86_URL" > /dev/null 2>&1
    if [ -f "$TMP_DIR/gecko64.msi" ]; then
        $wine_executable msiexec /i "$TMP_DIR/gecko64.msi" /qn
        if [ $? -eq 0 ]; then
            log_message "INFO" "Gecko x86_64 installed successfully."
        else
            log_message "ERROR" "Failed to install Gecko."
        fi
    else
        log_message "WARNING" "Failed to download Geckox86_64 Installer. Switching to Geckox86"
    fi
    if [ -f "$TMP_DIR/gecko32.msi" ]; then
        $wine_executable msiexec /i "$TMP_DIR/gecko32.msi" /qn
        if [ $? -eq 0 ]; then
            log_message "INFO" "Gecko x64 installed successfully."
        else
            log_message "ERROR" "Failed to install Gecko."
        fi
    else
        log_message "ERROR" "Failed to download Geckox86_64 & Geckox86 Installers."
    fi
    rm -rf "$TMP_DIR"
else
    log_message "INFO" "Wine Gecko already present."
fi