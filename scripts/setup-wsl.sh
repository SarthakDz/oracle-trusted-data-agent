#!/usr/bin/env bash
# One-time WSL setup for Trusted Data Agent: Docker Engine, Ollama, uv.
# Run inside WSL Ubuntu 22.04:  bash scripts/setup-wsl.sh
# Safe to re-run: each step is skipped when the tool is already installed.
set -euo pipefail

have() { command -v "$1" >/dev/null 2>&1; }

# Download to a file with retries before running it: piping curl straight into sh
# executes a truncated script when the connection drops mid-download.
fetch() {
  curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --connect-timeout 20 -o "$2" "$1"
}

echo "==> Docker Engine"
if ! have docker; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
sudo systemctl enable --now docker
if ! id -nG "$USER" | grep -qw docker; then
  sudo usermod -aG docker "$USER"
  echo "    Added $USER to the docker group. It takes effect after 'wsl --shutdown' or 'newgrp docker'."
fi

# GitHub release downloads crawl on some networks (measured 6.5 KB/s here), and both
# the Ollama and uv installers fetch from GitHub. Docker Hub and PyPI stay fast, so:
# uv comes from PyPI, and the Ollama binary is copied out of the official image.

echo "==> uv (from PyPI)"
if ! have uv && [ ! -x "$HOME/.local/bin/uv" ]; then
  python3 -m pip install --user uv
fi

echo "==> Ollama (copied from the official ollama/ollama image into ~/.local)"
if ! have ollama && [ ! -x "$HOME/.local/bin/ollama" ]; then
  docker pull ollama/ollama:latest
  cid=$(docker create ollama/ollama:latest)
  mkdir -p "$HOME/.local/bin" "$HOME/.local/lib"
  docker cp "$cid:/usr/bin/ollama" "$HOME/.local/bin/ollama"
  docker cp "$cid:/usr/lib/ollama" "$HOME/.local/lib/ollama"
  docker rm "$cid" >/dev/null
fi

echo "==> Memory"
mem_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
if [ "$mem_gb" -lt 11 ]; then
  echo "    WSL has ${mem_gb} GB RAM. Oracle + a local LLM need about 12 GB."
  echo "    On Windows, put these two lines in C:\\Users\\<you>\\.wslconfig:"
  echo "      [wsl2]"
  echo "      memory=12GB"
  echo "    then run 'wsl --shutdown' in PowerShell (this closes all WSL windows)."
fi

echo "==> Versions"
docker --version
docker compose version
"$HOME/.local/bin/ollama" --version 2>/dev/null || ollama --version 2>/dev/null || true
if have uv; then uv --version; else "$HOME/.local/bin/uv" --version; fi
echo "    Start the model server with 'make llm-up' (runs 'ollama serve' in the background)."
