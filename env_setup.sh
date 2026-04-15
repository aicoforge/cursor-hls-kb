#!/bin/bash
# Copyright (c) 2026 AICOFORGE. All rights reserved.
# CC BY-NC 4.0 — non-commercial use only. See LICENSE.
# Commercial use: kevinjan@aicoforge.com

# Ubuntu 20.04 / 22.04 Environment Detection and Auto-Installation Script
# Packages: Docker Engine, Docker Compose, Python3, curl

set -e

CURRENT_USER="${SUDO_USER:-$USER}"
DOCKER_ADDED=false
APT_UPDATED=false

log()  { echo "[i] $*"; }
ok()   { echo "[✓] $*"; }
warn() { echo "[!] $*"; }
err()  { echo "[✗] $*"; exit 1; }

apt_update_once() {
    if [ "$APT_UPDATED" = false ]; then
        apt-get update -qq
        APT_UPDATED=true
    fi
}

# ── Permission & OS Check ────────────────────────────────────
[ "$EUID" -ne 0 ] && err "Please run with sudo: sudo bash $0"

. /etc/os-release
[[ "$ID" != "ubuntu" ]] && err "This script only supports Ubuntu, detected: $ID"
log "Ubuntu $VERSION_ID | User: $CURRENT_USER"

# ── 1. curl ──────────────────────────────────────────────────
echo ""
log "--- 1. curl ---"
if command -v curl &>/dev/null; then
    ok "curl $(curl --version | head -1 | awk '{print $2}') already installed"
else
    warn "curl not installed, installing..."
    apt_update_once
    apt-get install -y curl
    ok "curl $(curl --version | head -1 | awk '{print $2}') installation complete"
fi

# ── 2. Python3 ───────────────────────────────────────────────
echo ""
log "--- 2. Python3 ---"
if command -v python3 &>/dev/null; then
    ok "python3 $(python3 --version 2>&1 | awk '{print $2}') already installed"
else
    warn "python3 not installed, installing..."
    apt_update_once
    apt-get install -y python3
    ok "python3 $(python3 --version 2>&1 | awk '{print $2}') installation complete"
fi

# ── 3. pip3 & Python Packages ────────────────────────────────
echo ""
log "--- 3. pip3 & Python Packages ---"
if command -v pip3 &>/dev/null; then
    ok "pip3 $(pip3 --version | awk '{print $2}') already installed"
else
    warn "pip3 not installed, installing..."
    apt_update_once
    apt-get install -y python3-pip
    ok "pip3 $(pip3 --version | awk '{print $2}') installation complete"
fi

# pip >= 23 supports --break-system-packages (Ubuntu 22.04 ships pip 22.x)
PIP_MAJOR=$(pip3 --version | awk '{print $2}' | cut -d. -f1)
if [ "$PIP_MAJOR" -ge 23 ]; then
    PIP_EXTRA="--break-system-packages"
else
    PIP_EXTRA=""
fi

PY_PKGS=(asyncpg pyyaml)
for pkg in "${PY_PKGS[@]}"; do
    if pip3 show "$pkg" &>/dev/null 2>&1; then
        ok "Python package $pkg already installed"
    else
        warn "Installing Python package: $pkg ..."
        PIP_NO_WARN_SCRIPT_LOCATION=1 pip3 install $PIP_EXTRA -q "$pkg" 2>/dev/null
        ok "Python package $pkg installation complete"
    fi
done

# ── 4. Docker Engine ─────────────────────────────────────────
echo ""
log "--- 4. Docker Engine ---"
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ',') already installed and running"
elif command -v docker &>/dev/null; then
    warn "Docker installed but service not running, attempting to start..."
    systemctl enable docker && systemctl start docker
    ok "Docker service started"
else
    warn "Docker not installed, installing..."
    apt_update_once
    apt-get install -y ca-certificates gnupg lsb-release
    apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    systemctl enable docker && systemctl start docker
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ',') installation complete"
fi

# ── 5. Docker Compose ────────────────────────────────────────
echo ""
log "--- 5. Docker Compose ---"
if docker compose version &>/dev/null 2>&1; then
    ok "docker compose $(docker compose version --short 2>/dev/null || echo plugin) already installed"
elif command -v docker-compose &>/dev/null; then
    ok "docker-compose $(docker-compose --version | awk '{print $NF}' | tr -d ',') already installed"
else
    warn "Docker Compose not installed, installing..."
    apt-get install -y docker-compose-plugin 2>/dev/null || apt-get install -y docker-compose 2>/dev/null || true

    if docker compose version &>/dev/null 2>&1; then
        ok "docker compose plugin installation complete"
    else
        log "Downloading standalone binary..."
        COMPOSE_VER=$(curl -s https://api.github.com/repos/docker/compose/releases/latest \
            | grep '"tag_name"' | cut -d'"' -f4)
        curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VER}/docker-compose-linux-x86_64" \
            -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
        ok "docker-compose $(docker-compose --version | awk '{print $NF}' | tr -d ',') installation complete"
    fi
fi

# Create docker-compose symlink for backward compatibility with docker compose plugin
if docker compose version &>/dev/null 2>&1 && ! command -v docker-compose &>/dev/null; then
    PLUGIN_PATH="/usr/libexec/docker/cli-plugins/docker-compose"
    [ ! -f "$PLUGIN_PATH" ] && PLUGIN_PATH="/usr/lib/docker/cli-plugins/docker-compose"
    if [ -f "$PLUGIN_PATH" ]; then
        ln -sf "$PLUGIN_PATH" /usr/local/bin/docker-compose
        ok "Created docker-compose symlink (backward compatibility)"
    fi
fi

# ── 6. Docker Group Setup ────────────────────────────────────
echo ""
log "--- 6. Docker Group Setup ---"
getent group docker &>/dev/null || groupadd docker

if id -nG "$CURRENT_USER" | grep -qw docker; then
    ok "$CURRENT_USER is already in the docker group"
else
    usermod -aG docker "$CURRENT_USER"
    ok "Added $CURRENT_USER to the docker group"
    DOCKER_ADDED=true
fi

if [ -S /var/run/docker.sock ]; then
    chmod 660 /var/run/docker.sock
    chown root:docker /var/run/docker.sock
fi

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "=============================="
echo " Environment Check Complete"
echo "=============================="
printf "%-16s %s\n" "curl"    "$(curl --version | head -1 | awk '{print $2}')"
printf "%-16s %s\n" "python3" "$(python3 --version 2>&1 | awk '{print $2}')"
printf "%-16s %s\n" "docker"  "$(docker --version | awk '{print $3}' | tr -d ',')"
if command -v docker-compose &>/dev/null; then
    printf "%-16s %s\n" "docker-compose" "$(docker-compose --version | awk '{print $NF}' | tr -d ',')"
fi
echo ""

if [ "$DOCKER_ADDED" = true ]; then
    echo "[✓] Installation complete! Run the following command to apply docker group (one-time only):"
    echo ""
    echo "    newgrp docker"
    echo ""
else
    ok "All setup complete, environment is ready!"
fi
