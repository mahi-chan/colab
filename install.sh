#!/usr/bin/env sh
# thesis-mcp installer for macOS and Linux.
#
#   ./install.sh                      install into every AI client found on this computer
#   ./install.sh --client cursor      install into one client (repeatable)
#   ./install.sh --print              only print the config entry, change nothing
#
# Run it from a checkout of the repository, or on its own (it then downloads the
# repository to ~/.thesis-mcp/app). Safe to run again: it updates and re-registers.
set -eu

REPO_URL="${THESIS_MCP_REPO:-https://github.com/mahi-chan/colab.git}"
BRANCH="${THESIS_MCP_BRANCH:-claude/mcp-colab-kaggle-3nheg4}"
APP_DIR="${THESIS_MCP_DIR:-$HOME/.thesis-mcp/app}"

say() { printf '%s\n' "$*"; }
fail() { say "error: $*" >&2; exit 1; }

# 1. Find the code: this checkout if we are in one, otherwise download it.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || pwd)
if [ -f "$SCRIPT_DIR/pyproject.toml" ] && grep -q '^name = "thesis-mcp"' "$SCRIPT_DIR/pyproject.toml"; then
    APP_DIR="$SCRIPT_DIR"
    say "Using the checkout at $APP_DIR"
else
    command -v git >/dev/null 2>&1 || fail "git is required. Install it, then run this again."
    if [ -d "$APP_DIR/.git" ]; then
        say "Updating $APP_DIR"
        git -C "$APP_DIR" pull --ff-only --quiet
    else
        say "Downloading thesis-mcp to $APP_DIR"
        mkdir -p "$(dirname "$APP_DIR")"
        git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
    fi
fi

# 2. Make sure uv (the Python package manager this project uses) is available.
PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export PATH
if ! command -v uv >/dev/null 2>&1; then
    say "Installing uv (https://docs.astral.sh/uv/)"
    command -v curl >/dev/null 2>&1 || fail "curl is required to install uv. Install uv yourself, then run this again."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    command -v uv >/dev/null 2>&1 || fail "uv was installed but is not on PATH. Open a new terminal and run this again."
fi

# 3. Create the environment with the exact pinned versions.
say "Installing dependencies"
cd "$APP_DIR"
uv sync --locked --no-dev --inexact --quiet

# 4. Register with AI clients.
say ""
uv run --no-sync thesis-mcp install "$@"
