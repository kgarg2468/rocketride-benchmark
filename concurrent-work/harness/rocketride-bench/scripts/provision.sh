#!/usr/bin/env bash
# Provision a reproducible environment: locate-or-download the PINNED RocketRide runtime and
# build the harness venv. No credentials needed — the engine is a public MIT release.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RR_ENGINE_VERSION="${RR_ENGINE_VERSION:-3.2.1}"
ENGINE_DIR="${ENGINE_DIR:-$REPO_DIR/engine}"

# 1) Engine: use an existing one, else download the prebuilt for this OS/arch.
if [ -x "$ENGINE_DIR/engine" ]; then
  echo "engine present: $ENGINE_DIR/engine"
else
  os="$(uname -s)"; arch="$(uname -m)"
  case "$os/$arch" in
    Darwin/arm64) plat=darwin-arm64 ;;
    Darwin/x86_64) plat=darwin-x64 ;;
    Linux/*)      plat=linux-x64 ;;
    *) echo "unsupported $os/$arch; use Docker (ghcr.io/rocketride-org/rocketride-engine)"; exit 1 ;;
  esac
  asset="rocketride-server-v${RR_ENGINE_VERSION}-${plat}.tar.gz"
  url="https://github.com/rocketride-org/rocketride-server/releases/download/server-v${RR_ENGINE_VERSION}/${asset}"
  echo "downloading $url"
  mkdir -p "$ENGINE_DIR"
  curl -fL "$url" -o "/tmp/$asset"
  tar -xzf "/tmp/$asset" -C "$ENGINE_DIR" --strip-components=1
  echo "extracted engine -> $ENGINE_DIR"
fi
( cd "$ENGINE_DIR" && ./engine --version 2>&1 | head -1 ) || true

# NOTE: native prebuilts exist for darwin-arm64/darwin-x64/linux-x64/win64. On Apple Silicon the
# Docker image (linux-x64) runs under emulation — for fair Mac numbers use the darwin-arm64
# prebuilt; for fair Docker numbers run on a linux-x64 host and containerize the competitors too.

# 2) Harness venv.
if [ ! -x "$REPO_DIR/.venv/bin/python" ]; then
  echo "creating venv"
  python3 -m venv "$REPO_DIR/.venv"
fi
"$REPO_DIR/.venv/bin/python" -m pip install --quiet --upgrade pip
"$REPO_DIR/.venv/bin/python" -m pip install --quiet -r "$REPO_DIR/requirements.txt"
echo "venv ready: $REPO_DIR/.venv  ($("$REPO_DIR/.venv/bin/python" -c 'import rocketride; print("rocketride", rocketride.__version__)'))"

# 3) Optional: the REAL LangChain competitor baseline for the Tier-1 head-to-heads (no infra, no
#    creds — the model is a fixed-latency mock). `make provision-competitors` does the same thing.
if [ "${1:-}" = "--competitors" ]; then
  echo "installing competitor baselines (real LangChain)"
  "$REPO_DIR/.venv/bin/python" -m pip install --quiet -r "$REPO_DIR/requirements-competitors.txt"
  echo "competitors ready: $("$REPO_DIR/.venv/bin/python" -c 'import langchain_core; print("langchain-core", langchain_core.__version__)')"
fi

echo
echo "provisioned. next:  make start  &&  make smoke"
echo "competitor head-to-heads (optional):  make provision-competitors  &&  make run-competitive"
