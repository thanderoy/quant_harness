# Stage 1: Base image with Wine and utilities
FROM ghcr.io/linuxserver/baseimage-kasmvnc:ubuntunoble-ffa21aaf-ls56

# Environment
ENV TITLE="MetaTrader" \
    WINEARCH=win64 \
    WINEPREFIX="/config/.wine" \
    DISPLAY=:0 \
    WINEDEBUG="-all,err-toolbar,fixme-all"

# Ensure the directory exists with correct permissions
RUN mkdir -p /config/.wine && \
    chown -R abc:abc /config/.wine && \
    chmod -R 755 /config/.wine

# Install System & Wine Dependencies
# Combined into a single layer for optimization
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        dos2unix \
        python3-pip \
        wget \
        python3-pyxdg \
        netcat-openbsd \
        cabextract

# Enable 32-bit architecture (must be BEFORE wine repo)
RUN dpkg --add-architecture i386 && \
    apt-get update -y

# Add WineHQ key
RUN mkdir -pm755 /etc/apt/keyrings && \
    wget -O - https://dl.winehq.org/wine-builds/winehq.key | sudo gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key - && \
    wget -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/ubuntu/dists/noble/winehq-noble.sources && \
    apt-get update && \
    apt-get install -y --install-recommends winehq-stable && \
    # Winetricks Setup
    apt-get purge winetricks -y && \
    wget -O /tmp/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks && \
    chmod +x /tmp/winetricks && \
    mv /tmp/winetricks /usr/local/bin && \
    # Cleanup
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*


# Application Setup
COPY app /app
COPY app/scripts /scripts

# Handle permissions and scripts
RUN dos2unix /scripts/*.sh && \
    chmod +x /scripts/*.sh && \
    # Create log file (Make sure your app writes here at runtime)
    touch /var/log/mt5_setup.log && \
    chown abc:abc /var/log/mt5_setup.log && \
    chmod 664 /var/log/mt5_setup.log

# S6 Overlay Configuration (Services, Init scripts)
COPY /root /

# Expose KasmVNC UI and FastAPI
EXPOSE 3000 8000 5001 8001 18812

VOLUME /config
