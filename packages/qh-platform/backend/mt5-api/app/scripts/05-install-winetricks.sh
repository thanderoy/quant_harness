#!/bin/bash

# Install common winetricks components for stability
source /scripts/02-common.sh

log_message "RUNNING" "05-install-winetricks.sh"

export WINEPREFIX="${WINEPREFIX:-/config/.wine}"
export WINEARCH="${WINEARCH:-win64}"

# Initialize wine prefix non-interactively
wineboot -u
winetricks -q settings win10

# Common components: vcrun2019, corefonts
# Note: --q to avoid prompts
winetricks -q ucrtbase2019 vcrun2019 corefonts

log_message "INFO" "Winetricks components installation complete."