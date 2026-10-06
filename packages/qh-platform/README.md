# MetaTrader5 on Wine with Python Setup

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Overview

Right off the bat!!! This project HEAVILY borrows inspiration from [Sesto's Project](https://github.com/sesto-dev/metatrader5-quant-server-python/tree/chapter-4).
It's basically an untethered fork.

This project provides a Dockerized setup to run MetaTrader5 (MT5) using Wine on an Ubuntu environment. It leverages Traefik as a reverse proxy for managing HTTP/HTTPS traffic and ensures secure access through Let's Encrypt certificates. The setup includes VNC for remote desktop access and is configured to run as a background service with proper logging and environment management.

## Features

- **Dockerized Environment:** Simplifies deployment, management and, scalability of MT5 instances.
- **Wine Compatibility:** Runs MetaTrader 5 on a Linux-based system.
- **Traefik Integration:** Handles reverse proxying with automatic SSL certificate generation via Let's Encrypt.
- **VNC Access:** Provides remote desktop access to the MT5 application.
- **Logging:** Implements structured logging for easy monitoring and debugging.
- **Environment Configuration:** Easily manage settings using environment variables.

## Prerequisites

- **Docker:** Ensure Docker is installed on your system. [Install Docker](https://docs.docker.com/get-docker/)
- **Docker Compose:** Required for orchestrating the services. [Install Docker Compose](https://docs.docker.com/compose/install/)
- **Domain Name:** A registered domain for accessing Traefik and VNC services.
- **SSL Certificate:** Managed automatically via Let's Encrypt.

## Installation

1. **Clone Repository:**

```bash
git clone https://github.com/thanderoy/wine-mt5-python-setup.git
cd wine-mt5-python-setup
```

2. **Environment Setup:**

```bash
cp .env.example .env
```

3. **Configure Environment:**

```env
# Required Variables
TRAEFIK_SERVICE_DOMAIN=traefik.yourdomain.com
VNC_DOMAIN=vnc.yourdomain.com
API_DOMAIN=api.yourdomain.com
DJANGO_SERVICE_DOMAIN=app.yourdomain.com

# Security
TRAEFIK_USERNAME=admin
TRAEFIK_HASHED_PASSWORD=your_hashed_password
ACME_EMAIL=your@email.com

# Database
POSTGRES_DB=mt5db
POSTGRES_USER=mt5user
POSTGRES_PASSWORD=securepassword
```

4. **Start Services:**

```bash
docker network create traefik-public
docker-compose up -d
```

## Configuration

### Environment Variables

- `CUSTOM_USER`: Username for accessing the MT5 service.
- `PASSWORD`: Password for the custom user.
- `VNC_DOMAIN`: Domain for accessing the VNC service.
- `TRAEFIK_SERVICE_DOMAIN`: Domain for Traefik dashboard.
- `TRAEFIK_USERNAME`: Username for Traefik basic authentication.
- `ACME_EMAIL`: Email address for Let's Encrypt notifications.

### Service Architecture

- **Traefik (Port 80, 443):** Reverse proxy, SSL termination
- **MT5 (Port 5001):** Trading platform API
- **VNC (Port 3000):** Remote desktop access
- **Django (Port 8000):** Web interface
- **PostgreSQL (Port 5432):** Database
- **Redis (Port 6379):** Cache and message broker

### Volumes

- `./config:/config`: Wine and MT5 configuration
- `postgres-data:/var/lib/postgresql/data`: Database persistence
- `static_volume:/app/staticfiles`: Django static files

## Usage

### Access Points

- MT5 VNC Interface: `https://vnc.yourdomain.com`
- API Endpoint: `https://api.yourdomain.com`
- Django Admin: `https://app.yourdomain.com/admin`
- Traefik Dashboard: `https://traefik.yourdomain.com`

### Common Commands

```bash
# View logs
docker-compose logs -f mt5

# Restart specific service
docker-compose restart mt5

# Check service status
docker-compose ps
```

## Logging

The setup uses JSON-file logging with the following configuration:

- **Log Driver:** `json-file`
- **Max Size:** `1m`
- **Max File:** `1`

Logs are managed per service and can be viewed using Docker commands or integrated with external logging solutions like Promtail.

## Troubleshooting

### Common Issues

1. **MT5 Container Fails to Start:**

   - Check Wine initialization logs
   - Verify SSL certificate permissions
   - Ensure sufficient system resources

2. **API Connection Issues:**

   - Verify MT5 terminal login credentials
   - Check network connectivity
   - Review API logs for errors

3. **SSL Certificate Errors:**
   - Ensure correct DNS configuration
   - Check Traefik logs
   - Verify ACME challenge access

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the [MIT License](LICENSE.md).
