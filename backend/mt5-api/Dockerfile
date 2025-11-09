# Stage 1: Base image with Wine and utilities
FROM ghcr.io/linuxserver/baseimage-kasmvnc:ubuntunoble-ffa21aaf-ls56 AS base

# Environment
ENV TITLE="MetaTrader" \
    WINEARCH=win64 \
    WINEPREFIX=/config/.wine \
    DISPLAY=:0 \
    WINEDEBUG=-all,err-toolbar,fixme-all

# System setup
RUN set -eux; \
    mkdir -p /config/.wine && \
    chown -R abc:abc /config && \
    chmod -R 755 /config && \
    apt-get update && apt-get upgrade -y && \
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
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# WineHQ repo
RUN set -eux; \
    mkdir -pm755 /etc/apt/keyrings; \
    wget -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key; \
    echo "deb [arch=amd64,i386 signed-by=/etc/apt/keyrings/winehq-archive.key] https://dl.winehq.org/wine-builds/ubuntu/ $(lsb_release -cs) main" > /etc/apt/sources.list.d/winehq.list; \
    dpkg --add-architecture i386; \
    apt-get update; \
    apt-get install -y --install-recommends winehq-stable; \
    rm -rf /var/lib/apt/lists/*

# Winetricks
RUN set -eux; \
    wget -O /usr/local/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks; \
    chmod +x /usr/local/bin/winetricks

# Stage 2: Final image
FROM base AS final

# Copy application and scripts
# - Place Python app at /app/app.py for Wine Python to run
# - Provide Windows requirements for Wine Python
WORKDIR /
COPY scripts /scripts
RUN dos2unix /scripts/*.sh && chmod +x /scripts/*.sh

# Create app dir and copy code/requirements
RUN mkdir -p /app
COPY main.py /app/app.py
COPY requirements.txt /app/requirements.txt

# Logs
RUN touch /var/log/mt5_setup.log && \
    chown abc:abc /var/log/mt5_setup.log && \
    chmod 644 /var/log/mt5_setup.log

# s6-overlay integration: init tasks and long-running service
RUN set -eux; \
    mkdir -p /etc/cont-init.d /etc/services.d/mt5; \
    printf "#!/usr/bin/with-contenv bash\nset -e\nmkdir -p /config/.wine\nchown -R abc:abc /config\nchmod -R 755 /config\n" > /etc/cont-init.d/20-wine-setup; \
    chmod +x /etc/cont-init.d/20-wine-setup; \
    printf "#!/usr/bin/with-contenv bash\nexec s6-setuidgid abc /bin/bash /scripts/01-start.sh\n" > /etc/services.d/mt5/run; \
    chmod +x /etc/services.d/mt5/run

# Expose KasmVNC UI and FastAPI
EXPOSE 3000 8000 18812

VOLUME /config
