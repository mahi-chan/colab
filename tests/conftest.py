"""Shared test setup.

Environment is fixed *before* thesis_mcp is imported, so tests never touch the real
state directory, a real Hugging Face login, or a real runtime.
"""

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from unittest import mock

import pytest

os.environ["THESIS_STATE_DIR"] = tempfile.mkdtemp(prefix="thesis-mcp-test-state-")
os.environ["HF_TOKEN"] = "hf_test_token"
for _var in ("JUPYTER_URL", "JUPYTER_TOKEN", "THESIS_CONTENTS_ROOT", "THESIS_RUN_ROOT"):
    os.environ.pop(_var, None)

from huggingface_hub import HfApi  # noqa: E402

from thesis_mcp import runtime_state as rs  # noqa: E402
from thesis_mcp import server  # noqa: E402
from thesis_mcp.connectors import hf  # noqa: E402

STUBS = str(Path(__file__).parent / "stubs")
JUPYTER_TOKEN = "test-jupyter-token"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_jupyter(url: str, token: str, proc: subprocess.Popen, seconds: int = 60) -> None:
    for _ in range(seconds * 2):
        if proc.poll() is not None:
            raise RuntimeError(f"jupyter exited early with code {proc.returncode}")
        try:
            req = urllib.request.Request(f"{url}/api/status", headers={"Authorization": f"token {token}"})
            if urllib.request.urlopen(req, timeout=2).status == 200:
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("jupyter did not come up")


def remote_env(stub_log: Path) -> dict:
    """Environment of the simulated remote machine: stub Hub client, no HF login."""
    env = dict(os.environ)
    env.pop("HF_TOKEN", None)
    env["PYTHONPATH"] = STUBS
    env["HF_STUB_LOG"] = str(stub_log)
    return env


def call(tool: str, /, **kwargs):
    """Call a tool through the real MCP path. Returns (text, [content block type names])."""
    result = asyncio.run(server.mcp.call_tool(tool, kwargs))
    blocks = result[0] if isinstance(result, tuple) else result
    text = "\n".join(getattr(b, "text", "") for b in blocks)
    return text, [type(b).__name__ for b in blocks]


@pytest.fixture(autouse=True)
def hub():
    """Replace the Hugging Face client with a spec-checked mock.

    ``create_autospec`` rejects any call that does not match the installed library's
    real method signatures, so a wrong argument name fails here instead of in production.
    """
    fake = mock.create_autospec(HfApi, instance=True)
    fake.whoami.return_value = {"name": "alice", "orgs": [], "canPay": True,
                                "auth": {"accessToken": {"role": "write"}}}
    hf._api = fake
    yield fake
    hf._api = None


@pytest.fixture(autouse=True)
def clean_state():
    """Each test starts with no connection, no runs and no Hugging Face runtime."""
    rs.store.data = {"kernel": {}, "runs": {}}
    rs.jupyter.disconnect()
    yield
    rs.jupyter.disconnect()


@pytest.fixture(scope="session")
def jupyter_server(tmp_path_factory):
    """A real Jupyter server standing in for the remote machine."""
    root = tmp_path_factory.mktemp("remote-root")
    stub_log = tmp_path_factory.mktemp("stub") / "hub_calls.jsonl"
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "jupyter_server", "--ServerApp.ip=127.0.0.1",
         f"--ServerApp.port={port}", "--ServerApp.port_retries=0",
         f"--IdentityProvider.token={JUPYTER_TOKEN}", "--ServerApp.disable_check_xsrf=True",
         "--no-browser", "--allow-root", f"--ServerApp.root_dir={root}"],
        env=remote_env(stub_log), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        wait_for_jupyter(url, JUPYTER_TOKEN, proc)
        yield {"url": url, "token": JUPYTER_TOKEN, "root": root, "stub_log": stub_log}
    finally:
        proc.terminate()
        proc.wait(timeout=20)


@pytest.fixture
def runtime(jupyter_server):
    """The MCP connected to the stand-in remote machine."""
    text, _ = call("connect_runtime", url=jupyter_server["url"], token=jupyter_server["token"])
    assert "kernel" in text, text
    return jupyter_server


def wait_until_stopped(run_name: str, seconds: int = 60) -> str:
    for _ in range(seconds):
        status, _ = call("get_run_status", run_name=run_name)
        if "not running" in status:
            return status
        time.sleep(1)
    raise AssertionError(f"run {run_name} did not finish:\n{status}")
