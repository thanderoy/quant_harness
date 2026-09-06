#!/bin/bash

# Set variables
mt5setup_url="https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
mt5file="/config/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"
python_url="https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe"
wine_executable="wine"
metatrader_version="5.4.80"
mt5server_port=18812

# Function to show messages
log_message() {
    local level=$1
    local message=$2
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [$level] $message" | tee -a /tmp/mt5_setup.log
}

# Function to check if a Python package is installed in Wine
is_wine_python_package_installed() {
    $wine_executable python -c "import pkg_resources; pkg_resources.require('$1')" 2>/dev/null
    return $?
}

# Function to check if a Python package is installed in Linux
is_python_package_installed() {
    python3 -c "import pkg_resources; pkg_resources.require('$1')" 2>/dev/null
    return $?
}

# Mute Unnecessary Wine Errors
export WINEDEBUG=-all,err-toolbar,fixme-all

# --- Service liveness helpers -------------------------------------------------
# Shared by 09-start-wine-fastapi.sh (initial start) and 10-supervise.sh
# (restart-on-death). Both the MT5 terminal and the FastAPI server are started
# with '&' and are not supervised by s6, so if either dies the container stays
# up with a dead API. These helpers make that state detectable and recoverable.

api_port="${MT5_API_PORT:-5001}"

# True if the FastAPI server answers on its own port.
#
# NOT sufficient on its own: the service answers 200 whether or not it holds a
# link to the terminal, which is the state both containers sat in after their
# restarts. Use api_connected() for "is this container actually usable".
api_responding() {
    wget -qO- --timeout=10 "http://localhost:${api_port}/" >/dev/null 2>&1
}

# True if the service answers AND reports a live terminal link.
api_connected() {
    wget -qO- --timeout=10 "http://localhost:${api_port}/" 2>/dev/null \
        | grep -q '"mt5_connected":"True"'
}

# The service does not re-establish the terminal link on its own; it exposes
# /api/v1/connect and says so in its own 503 body. Calling it is what turns a
# responding-but-useless container back into a working one.
api_connect() {
    wget -qO- --timeout=60 --post-data='{}' \
        --header='Content-Type: application/json' \
        "http://localhost:${api_port}/api/v1/connect" >/dev/null 2>&1
}

# Health for supervision purposes: responding is not enough.
api_healthy() {
    api_connected
}

# True if the Wine MT5 terminal process is present.
terminal_running() {
    pgrep -f "terminal64.exe" >/dev/null 2>&1
}

# True if the Wine python process hosting the API is present.
fastapi_running() {
    pgrep -f "main.py" >/dev/null 2>&1
}

# Start the MT5 terminal under Wine if it is not already running.
ensure_terminal() {
    if terminal_running; then
        return 0
    fi
    if [ ! -e "$mt5file" ]; then
        log_message "ERROR" "Cannot start terminal: $mt5file is missing."
        return 1
    fi
    log_message "INFO" "Starting MT5 terminal..."
    $wine_executable "$mt5file" &
    sleep 20
    terminal_running
}

# Start the FastAPI server under Wine. Does not check health; callers poll.
start_fastapi() {
    log_message "INFO" "Starting FastAPI server in Wine environment..."
    $wine_executable python /app/main.py &
}

# Poll api_responding() until it succeeds or the budget is exhausted.
# Usage: wait_for_responding <attempts> <sleep_seconds>
wait_for_responding() {
    local attempts="${1:-30}"
    local gap="${2:-10}"
    local i=0
    while [ "$i" -lt "$attempts" ]; do
        if api_responding; then
            return 0
        fi
        i=$((i + 1))
        sleep "$gap"
    done
    return 1
}
