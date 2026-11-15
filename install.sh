#!/usr/bin/env sh
# gpu-bridge installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/mahi-chan/gpu-bridge/main/install.sh | sh
#
# It downloads gpu-bridge to ~/.gpu-bridge/app, sets up its Python environment, registers
# it with every AI client found on this computer, and adds a `gpu-bridge` command.
# Run the same line again to update. Options go after `sh -s --`, for example:
#
#   curl -fsSL <same address> | sh -s -- --client cursor
#
# Inside a checkout of the repository, `./install.sh` installs from that checkout instead.
set -eu

REPO="${GPU_BRIDGE_REPO_SLUG:-mahi-chan/gpu-bridge}"
BRANCH="${GPU_BRIDGE_BRANCH:-main}"
APP_DIR="${GPU_BRIDGE_DIR:-$HOME/.gpu-bridge/app}"
BIN_DIR="${GPU_BRIDGE_BIN:-$HOME/.local/bin}"

say() { printf '%s\n' "$*"; }
# Download a URL to stdout with curl, or wget on systems without curl.
fetch() {
    if command -v curl >/dev/null 2>&1; then curl -fsSL "$1"
    elif command -v wget >/dev/null 2>&1; then wget -qO- "$1"
    else fail "curl or wget is required."; fi
}
fail() { say "error: $*" >&2; exit 1; }

# 1. Find the code: this checkout if we are in one, otherwise download it.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || pwd)
if [ -f "$SCRIPT_DIR/pyproject.toml" ] && grep -q '^name = "gpu-bridge"' "$SCRIPT_DIR/pyproject.toml"; then
    APP_DIR="$SCRIPT_DIR"
    say "Using the checkout at $APP_DIR"
else
    command -v tar >/dev/null 2>&1 || fail "tar is required."
    say "Downloading gpu-bridge to $APP_DIR"
    NEW="$APP_DIR.new"
    rm -rf "$NEW"
    mkdir -p "$NEW"
    fetch "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$NEW" --strip-components=1 \
        || fail "could not download https://github.com/$REPO (branch $BRANCH)."
    # keep the existing environment so an update is quick
    if [ -d "$APP_DIR/.venv" ]; then mv "$APP_DIR/.venv" "$NEW/.venv"; fi
    rm -rf "$APP_DIR"
    mv "$NEW" "$APP_DIR"
fi

# 2. Make sure uv (the Python package manager this project uses) is available.
PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export PATH
if ! command -v uv >/dev/null 2>&1; then
    say "Installing uv (https://docs.astral.sh/uv/)"
    fetch https://astral.sh/uv/install.sh | sh
    command -v uv >/dev/null 2>&1 || fail "uv was installed but is not on PATH. Open a new terminal and run this again."
fi

# 3. Create the environment with the exact pinned versions.
say "Installing dependencies"
cd "$APP_DIR"
uv sync --locked --no-dev --inexact --quiet

# 4. Add a `gpu-bridge` command.
mkdir -p "$BIN_DIR"
printf '#!/bin/sh\nexec "%s/.venv/bin/gpu-bridge" "$@"\n' "$APP_DIR" > "$BIN_DIR/gpu-bridge"
chmod +x "$BIN_DIR/gpu-bridge"

# 5. Register with AI clients.
say ""
"$APP_DIR/.venv/bin/gpu-bridge" install "$@"

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) say ""
       say "Note: add $BIN_DIR to your PATH to use the 'gpu-bridge' command by name." ;;
esac
