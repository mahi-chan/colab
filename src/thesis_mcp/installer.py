"""Register this MCP server with AI clients (Claude Code, Cursor, VS Code, ...).

Every client keeps a small config file that says how to start each MCP server. The
installer adds one entry — "start this Python environment's ``thesis_mcp`` module" — and
leaves everything else in the file alone. No secret is ever written: the Hugging Face
token comes from ``hf auth login``, and a Colab/Kaggle address is given in chat.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

SERVER_NAME = "thesis"


class InstallError(RuntimeError):
    pass


def server_command() -> List[str]:
    """How a client starts the server: this environment's Python, by absolute path.

    Absolute, because desktop apps do not inherit the shell's PATH.
    """
    return [sys.executable, "-m", "thesis_mcp"]


def cli_command() -> str:
    """The `thesis-mcp` program of this installation, by full path, for messages."""
    name = "thesis-mcp.exe" if sys.platform == "win32" else "thesis-mcp"
    return f'"{Path(sys.executable).parent / name}"'


def server_entry(extra: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    command = server_command()
    return {**(extra or {}), "command": command[0], "args": command[1:]}


# -- where each client keeps its config ---------------------------------------
def _home() -> Path:
    return Path.home()


def _app_config_dir(app: str) -> Path:
    """Per-user config folder of a desktop app on this operating system."""
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / app
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or _home() / "AppData" / "Roaming") / app
    return Path(os.environ.get("XDG_CONFIG_HOME") or _home() / ".config") / app


def _vscode_user_dir() -> Path:
    return _app_config_dir("Code") / "User"


@dataclass
class Client:
    key: str
    label: str
    path: Callable[[], Path]
    fmt: str = "json"                      # "json", "toml" or "claude-cli"
    root_key: str = "mcpServers"
    extra: Dict[str, str] = field(default_factory=dict)
    after: str = "Restart the app to load it."

    def detected(self) -> bool:
        """True when the client looks installed on this computer."""
        if self.fmt == "claude-cli":
            return shutil.which("claude") is not None
        path = self.path()
        # Cline keeps its file in a "settings" folder inside its extension storage.
        marker = path.parents[1] if self.key == "cline" else path.parent
        return path.exists() or marker.is_dir()


CLIENTS: Dict[str, Client] = {c.key: c for c in [
    Client("claude-code", "Claude Code", lambda: _home() / ".claude.json", fmt="claude-cli",
           after="Start a new Claude Code session (or run /mcp) to load it."),
    Client("claude-desktop", "Claude Desktop",
           lambda: _app_config_dir("Claude") / "claude_desktop_config.json",
           after="Quit Claude Desktop completely and open it again."),
    Client("cursor", "Cursor", lambda: _home() / ".cursor" / "mcp.json",
           after="Restart Cursor, then enable 'thesis' under Settings > MCP if it is off."),
    Client("vscode", "VS Code (GitHub Copilot)", lambda: _vscode_user_dir() / "mcp.json",
           root_key="servers", extra={"type": "stdio"},
           after="Reload VS Code; the tools appear in Copilot Chat's agent mode."),
    Client("windsurf", "Windsurf", lambda: _home() / ".codeium" / "windsurf" / "mcp_config.json",
           after="Restart Windsurf (or press refresh in its MCP panel)."),
    Client("cline", "Cline (VS Code extension)",
           lambda: _vscode_user_dir() / "globalStorage" / "saoudrizwan.claude-dev" / "settings"
           / "cline_mcp_settings.json",
           after="Reload VS Code."),
    Client("gemini", "Gemini CLI", lambda: _home() / ".gemini" / "settings.json",
           after="Start a new Gemini CLI session."),
    Client("codex", "Codex CLI", lambda: _home() / ".codex" / "config.toml", fmt="toml",
           after="Start a new Codex session."),
]}


# -- JSON config files --------------------------------------------------------
def _read_json(path: Path) -> dict:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(
            f"{path} is not plain JSON ({exc.msg}, line {exc.lineno}); it may contain comments. "
            "Not touching it. Add this entry by hand instead:\n" + snippet()
        ) from None
    if not isinstance(data, dict):
        raise InstallError(f"{path} does not hold a JSON object; not touching it.")
    return data


def _write(path: Path, text: str) -> None:
    """Replace ``path`` atomically, keeping the previous version next to it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _json_install(client: Client, remove: bool) -> bool:
    path = client.path()
    data = _read_json(path)
    servers = data.get(client.root_key)
    if servers is None:
        servers = {}
    if not isinstance(servers, dict):
        raise InstallError(f'"{client.root_key}" in {path} is not an object; not touching it.')
    before = servers.get(SERVER_NAME)
    if remove:
        if before is None:
            return False
        del servers[SERVER_NAME]
    else:
        entry = server_entry(client.extra)
        if before == entry:
            return False
        servers[SERVER_NAME] = entry
    data[client.root_key] = servers
    _write(path, json.dumps(data, indent=2) + "\n")
    return True


def _json_installed(client: Client) -> bool:
    try:
        servers = _read_json(client.path()).get(client.root_key) or {}
    except InstallError:
        return False
    return isinstance(servers, dict) and SERVER_NAME in servers


# -- Codex (TOML) -------------------------------------------------------------
_TOML_BLOCK = re.compile(
    rf"(?ms)^\[mcp_servers\.{SERVER_NAME}(?:\.[^\]]*)?\]\n.*?(?=^\[|\Z)")


def _toml_block() -> str:
    command = server_command()
    args = ", ".join(json.dumps(a) for a in command[1:])  # JSON strings are valid TOML strings
    return f"[mcp_servers.{SERVER_NAME}]\ncommand = {json.dumps(command[0])}\nargs = [{args}]\n"


def _toml_install(client: Client, remove: bool) -> bool:
    path = client.path()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    stripped = _TOML_BLOCK.sub("", text)
    if remove:
        new = stripped
    else:
        new = stripped.rstrip("\n")
        new = (new + "\n\n" if new else "") + _toml_block()
    if new == text:
        return False
    try:
        import tomllib
        tomllib.loads(new)
    except ImportError:
        pass  # Python 3.10: no TOML parser in the standard library, skip the self-check
    except Exception as exc:
        raise InstallError(f"Editing {path} would leave it invalid ({exc}); not touching it. "
                           "Add this by hand instead:\n" + _toml_block()) from None
    _write(path, new)
    return True


def _toml_installed(client: Client) -> bool:
    path = client.path()
    return path.exists() and bool(_TOML_BLOCK.search(path.read_text(encoding="utf-8")))


# -- Claude Code (its own command line) ---------------------------------------
def _claude(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["claude", "mcp", *args], capture_output=True, text=True, timeout=120)


def _claude_user_entry() -> Optional[dict]:
    """The user-scope entry Claude Code has stored, read straight from its config file."""
    try:
        data = json.loads((_home() / ".claude.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"][SERVER_NAME]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return entry if isinstance(entry, dict) else None


def _claude_installed() -> bool:
    return _claude_user_entry() is not None


def _claude_install(remove: bool) -> bool:
    if shutil.which("claude") is None:
        raise InstallError("The `claude` command was not found. Install Claude Code first, "
                           "or add the server by hand:\n" + snippet())
    current = _claude_user_entry()
    command = server_command()
    if remove:
        return current is not None and _claude("remove", SERVER_NAME, "-s", "user").returncode == 0
    if current and current.get("command") == command[0] and current.get("args") == command[1:]:
        return False
    if current:
        _claude("remove", SERVER_NAME, "-s", "user")
    done = _claude("add", SERVER_NAME, "-s", "user", "--", *command)
    if done.returncode != 0:
        raise InstallError(f"`claude mcp add` failed: {(done.stderr or done.stdout).strip()}")
    return True


# -- public API ---------------------------------------------------------------
def snippet() -> str:
    """The entry to paste into any client that uses the common ``mcpServers`` format."""
    return json.dumps({"mcpServers": {SERVER_NAME: server_entry()}}, indent=2)


def is_installed(client: Client) -> bool:
    if client.fmt == "claude-cli":
        return _claude_installed()
    return _toml_installed(client) if client.fmt == "toml" else _json_installed(client)


def apply(client: Client, remove: bool = False) -> bool:
    """Install (or remove) the server for one client. Returns True if anything changed."""
    if client.fmt == "claude-cli":
        return _claude_install(remove)
    return _toml_install(client, remove) if client.fmt == "toml" else _json_install(client, remove)


def detected_clients() -> List[Client]:
    return [c for c in CLIENTS.values() if c.detected()]


def run(keys: List[str], remove: bool = False, dry_run: bool = False) -> int:
    """Command-line entry: install into (or remove from) the chosen or detected clients."""
    targets = [CLIENTS[k] for k in keys] if keys else detected_clients()
    verb = "Removing from" if remove else "Installing into"
    if not targets:
        print("No supported AI client was found on this computer.\n"
              f"Supported: {', '.join(CLIENTS)}.\n"
              f"Install into one anyway with:  {cli_command()} install --client <name>\n"
              "For any other client, add this to its MCP settings:\n" + snippet())
        return 1
    failed = 0
    for client in targets:
        where = "" if client.fmt == "claude-cli" else f"  ({client.path()})"
        if dry_run:
            print(f"[dry run] {verb} {client.label}{where}")
            continue
        try:
            changed = apply(client, remove=remove)
        except InstallError as exc:
            failed += 1
            print(f"[failed] {client.label}: {exc}")
            continue
        if remove:
            print(f"[ok] {client.label}: {'removed' if changed else 'was not installed'}{where}")
        else:
            state = "installed" if changed else "already up to date"
            print(f"[ok] {client.label}: {state}{where}\n     {client.after}")
    if not remove and not dry_run and failed < len(targets):
        print("\nNext: connect a machine to run on. Ask the assistant "
              f"\"how do I connect Colab / Kaggle / Hugging Face?\" or run:\n  {cli_command()} doctor")
    return 1 if failed else 0
