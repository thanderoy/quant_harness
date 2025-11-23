# Stage 1: Base image with Wine and utilities
FROM ghcr.io/linuxserver/baseimage-kasmvnc:ubuntunoble-ffa21aaf-ls56 AS base

# Environment
ENV TITLE="MetaTrader" \
    WINEARCH=win64 \
    WINEPREFIX="/config/.wine" \
    DISPLAY=:0 \
    WINEDEBUG="-all,err-toolbar,fixme-all" \
    DEBIAN_FRONTEND=noninteractive

# Ensure the directory exists with correct permissions (will be a volume at runtime)
RUN mkdir -p /config/.wine && \
    chown -R abc:abc /config/.wine && \
    chmod -R 755 /config/.wine

# Base packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        dos2unix \
        python3-pip \
        wget \
        python3-pyxdg \
        netcat-openbsd \
        ca-certificates \
        lsb-release \
        cabextract \
        unzip \
        p7zip-full \
        gnupg && \
    rm -rf /var/lib/apt/lists/*

# Add WineHQ repository key and APT source
RUN mkdir -pm755 /etc/apt/keyrings && \
    wget -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key && \
    echo "deb [arch=amd64,i386 signed-by=/etc/apt/keyrings/winehq-archive.key] https://dl.winehq.org/wine-builds/ubuntu/ $(lsb_release -cs) main" > /etc/apt/sources.list.d/winehq.list

# Add i386 architecture and install Wine stable
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --install-recommends winehq-stable && \
    rm -rf /var/lib/apt/lists/*

# Install Winetricks
RUN wget -O /usr/local/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks && \
    chmod +x /usr/local/bin/winetricks

# Stage 2: Final image
FROM base

# App and scripts
WORKDIR /app
COPY app/ /app/
COPY app/scripts /scripts

# Normalize and make scripts executable
RUN dos2unix /scripts/*.sh && chmod +x /scripts/*.sh

# s6 cont-init hook to start our setup
COPY root/ /
RUN chmod +x /etc/cont-init.d/01-start

# Log file for setup
RUN touch /var/log/mt5_setup.log && \
    chown abc:abc /var/log/mt5_setup.log && \
    chmod 644 /var/log/mt5_setup.log

# Expose KasmVNC UI and FastAPI
EXPOSE 3000 8000 18812

VOLUME /config
