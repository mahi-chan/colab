"""The installer: registering the server with AI clients without disturbing their config."""

import asyncio
import json
import os
import shutil
import subprocess
import sys

import pytest
from conftest import call, free_port

from thesis_mcp import cli, installer


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A throwaway home directory with no AI clients in it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    return tmp_path


def entry():
    return {"command": sys.executable, "args": ["-m", "thesis_mcp"]}


def test_json_install_keeps_everything_else(home):
    path = home / ".cursor" / "mcp.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
    cursor = installer.CLIENTS["cursor"]

    assert installer.apply(cursor) is True
    data = json.loads(path.read_text())
    assert data == {"mcpServers": {"other": {"command": "x"}, "thesis": entry()}, "theme": "dark"}
    assert json.loads((home / ".cursor" / "mcp.json.bak").read_text())["mcpServers"] == {"other": {"command": "x"}}
    assert installer.is_installed(cursor)

    before = path.read_text()
    assert installer.apply(cursor) is False, "a second install must change nothing"
    assert path.read_text() == before

    assert installer.apply(cursor, remove=True) is True
    assert json.loads(path.read_text()) == {"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}
    assert installer.apply(cursor, remove=True) is False


def test_creates_missing_config_and_uses_each_clients_format(home):
    for key in ("claude-desktop", "windsurf", "gemini", "cline"):
        client = installer.CLIENTS[key]
        assert installer.apply(client) is True
        assert json.loads(client.path().read_text()) == {"mcpServers": {"thesis": entry()}}
    vscode = installer.CLIENTS["vscode"]
    installer.apply(vscode)
    assert json.loads(vscode.path().read_text()) == {"servers": {"thesis": {"type": "stdio", **entry()}}}


def test_config_with_comments_is_left_alone(home):
    path = home / ".cursor" / "mcp.json"
    path.parent.mkdir()
    original = '{\n  // my servers\n  "mcpServers": {}\n}\n'
    path.write_text(original)
    with pytest.raises(installer.InstallError, match="not plain JSON"):
        installer.apply(installer.CLIENTS["cursor"])
    assert path.read_text() == original


def test_codex_toml(home):
    tomllib = pytest.importorskip("tomllib")  # standard library from Python 3.11
    path = home / ".codex" / "config.toml"
    path.parent.mkdir()
    path.write_text('model = "o"\n\n[mcp_servers.thesis]\ncommand = "old"\n\n[mcp_servers.thesis.env]\nA = "1"\n\n'
                    '[mcp_servers.other]\ncommand = "x"\n')
    codex = installer.CLIENTS["codex"]

    assert installer.apply(codex) is True
    data = tomllib.loads(path.read_text())
    assert data["model"] == "o" and data["mcp_servers"]["other"] == {"command": "x"}
    assert data["mcp_servers"]["thesis"] == entry(), "the old entry and its sub-table are replaced"
    assert installer.apply(codex) is False

    assert installer.apply(codex, remove=True) is True
    assert "thesis" not in tomllib.loads(path.read_text())["mcp_servers"]


@pytest.mark.parametrize("platform, env, expected", [
    ("darwin", {}, "Library/Application Support/Claude/claude_desktop_config.json"),
    ("linux", {}, ".config/Claude/claude_desktop_config.json"),
    ("win32", {"APPDATA": "{home}/AppData/Roaming"}, "AppData/Roaming/Claude/claude_desktop_config.json"),
])
def test_claude_desktop_path_per_operating_system(home, monkeypatch, platform, env, expected):
    monkeypatch.setattr(sys, "platform", platform)
    for key, value in env.items():
        monkeypatch.setenv(key, value.format(home=home))
    assert installer.CLIENTS["claude-desktop"].path() == home / expected


def test_detection_and_default_targets(home, monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda name: None)  # no Claude Code on this "computer"
    assert installer.detected_clients() == []
    assert installer.run([]) == 1
    assert '"mcpServers"' in capsys.readouterr().out, "with nothing found, the manual entry is shown"

    (home / ".gemini").mkdir()
    installer._vscode_user_dir().mkdir(parents=True)
    assert [c.key for c in installer.detected_clients()] == ["vscode", "gemini"]
    assert installer.run([], dry_run=True) == 0
    assert not (home / ".gemini" / "settings.json").exists(), "a dry run writes nothing"
    assert installer.run([]) == 0
    assert installer.is_installed(installer.CLIENTS["gemini"]) and installer.is_installed(installer.CLIENTS["vscode"])
    assert installer.run([], remove=True) == 0
    assert not installer.is_installed(installer.CLIENTS["gemini"])


@pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code is not installed")
def test_claude_code_real_cli(home):
    claude = installer.CLIENTS["claude-code"]
    assert installer.apply(claude) is True
    stored = json.loads((home / ".claude.json").read_text())["mcpServers"]["thesis"]
    assert stored["command"] == sys.executable and stored["args"] == ["-m", "thesis_mcp"]
    assert installer.apply(claude) is False
    assert installer.apply(claude, remove=True) is True
    assert not installer.is_installed(claude)


def test_command_line(home, capsys):
    assert cli.main(["install", "--print"]) == 0
    assert json.loads(capsys.readouterr().out) == {"mcpServers": {"thesis": entry()}}

    assert cli.main(["install", "--client", "cursor"]) == 0
    assert "[ok] Cursor: installed" in capsys.readouterr().out
    assert cli.main(["clients"]) == 0
    row = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("cursor"))
    assert row.split()[1:3] == ["yes", "yes"]

    assert cli.main(["doctor"]) == 0
    report = capsys.readouterr().out
    assert "[installed] Cursor" in report and "Hugging Face: token found" in report
    assert cli.main(["uninstall", "--client", "cursor"]) == 0


def test_the_registered_command_starts_a_working_server(tmp_path):
    """Run exactly what the installer writes into client configs, and talk MCP to it."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command = installer.server_command()

    async def handshake():
        env = {**os.environ, "THESIS_STATE_DIR": str(tmp_path)}
        async with stdio_client(StdioServerParameters(command=command[0], args=command[1:], env=env)) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                return (await session.call_tool("list_runs", {})).content[0].text

    assert asyncio.run(handshake()) == "No runs yet."


def test_http_mode_for_clients_that_connect_by_url(tmp_path):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    port = free_port()
    env = {**os.environ, "THESIS_STATE_DIR": str(tmp_path)}
    proc = subprocess.Popen([*installer.server_command(), "serve", "--http", "--port", str(port)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def handshake():
        for _ in range(60):
            try:
                async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (r, w, _):
                    async with ClientSession(r, w) as session:
                        await session.initialize()
                        return len((await session.list_tools()).tools)
            except Exception:  # noqa: BLE001 - server still starting
                await asyncio.sleep(0.5)
        raise AssertionError("HTTP server did not come up")

    try:
        assert asyncio.run(handshake()) == 54
    finally:
        proc.terminate()
        proc.wait(timeout=20)


def test_setup_guide_and_examples_are_available_as_tools():
    overview, _ = call("setup_guide")
    assert "Hugging Face: token found" in overview and "Kaggle: not logged in" in overview

    assert "colab_runtime_start" in call("setup_guide", platform="colab")[0]
    kaggle_steps, _ = call("setup_guide", platform="Kaggle")
    assert "login kaggle" in kaggle_steps and "kaggle_runtime_start" in kaggle_steps
    assert "login huggingface" in call("setup_guide", platform="huggingface")[0]
    assert "hf_auth=True" in call("setup_guide", platform="space")[0]
    assert "Unknown platform" in call("setup_guide", platform="aws")[0]

    assert "llm_lora_finetune.py" in call("example_script")[0]
    assert "LoraConfig" in call("example_script", name="llm_lora_finetune")[0]
    assert "No example named" in call("example_script", name="nope")[0]


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_wheel_carries_the_remote_program_and_examples(tmp_path):
    import zipfile
    from pathlib import Path

    repo = Path(__file__).parent.parent
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(repo)],
                   check=True, capture_output=True)
    names = zipfile.ZipFile(next(tmp_path.glob("*.whl"))).namelist()
    for needed in ("thesis_mcp/_assets/examples/llm_lora_finetune.py",
                   "thesis_mcp/remote/entrypoint.py", "thesis_mcp/__main__.py"):
        assert needed in names, needed


def test_login_command_hands_over_to_the_platform_tools(monkeypatch):
    import subprocess as sp

    ran = []
    monkeypatch.setattr(sp, "call", lambda command: ran.append(command) or 0)
    assert cli.main(["login", "kaggle"]) == 0
    assert ran[-1] == [sys.executable, "-m", "kaggle", "auth", "login"]
    assert cli.main(["login", "huggingface"]) == 0
    assert ran[-1][1:] == ["auth", "login"] and os.path.basename(ran[-1][0]).startswith("hf")
    assert os.path.exists(ran[-1][0]), "the Hugging Face login program ships with the environment"
