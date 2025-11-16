# Stage 1: Base image with Wine and utilities
FROM ghcr.io/linuxserver/baseimage-kasmvnc:ubuntunoble-ffa21aaf-ls56 AS base

# Environment
ENV TITLE="MetaTrader"
ENV WINEARCH=win64
ENV WINEPREFIX="/config/.wine"
ENV DISPLAY=:0
ENV WINEDEBUG="-all,err-toolbar,fixme-all"

# Ensure the directory exists with correct permissions
RUN mkdir -p /config/.wine && \
    chown -R abc:abc /config/.wine && \
    chmod -R 755 /config/.wine


# Update package lists and upgrade packages
RUN apt-get update && apt-get upgrade -y

# Install required packages
RUN apt-get install -y \
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
    gnupg

# Add WineHQ repository key and APT source
RUN mkdir -pm755 /etc/apt/keyrings && \
    wget -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key && \
    echo "deb [arch=amd64,i386 signed-by=/etc/apt/keyrings/winehq-archive.key] https://dl.winehq.org/wine-builds/ubuntu/ $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/winehq.list

# Add i386 architecture and update package lists
RUN dpkg --add-architecture i386 && \
    apt-get update

# Install WineHQ stable package and dependencies
RUN apt-get install --install-recommends -y winehq-stable

# Install Winetricks
RUN wget -O /tmp/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks && \
    chmod +x /tmp/winetricks && \
    mv /tmp/winetricks /usr/local/bin/winetricks && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Stage 2: Final image
FROM base

# Copy the scripts directory and convert start.sh to Unix format
WORKDIR /
COPY scripts /scripts
COPY main.py .
COPY requirements.txt .

RUN dos2unix /scripts/*.sh && \
    chmod +x /scripts/*.sh

COPY /root /
RUN touch /var/log/mt5_setup.log && \
    chown abc:abc /var/log/mt5_setup.log && \
    chmod 644 /var/log/mt5_setup.log

# Expose KasmVNC UI and FastAPI
EXPOSE 3000 5000 5001 8001 18812

VOLUME /config
