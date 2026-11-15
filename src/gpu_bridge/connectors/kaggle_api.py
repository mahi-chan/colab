"""Kaggle, driven from this computer through the user's Kaggle login.

Used to start a GPU session without opening the browser (``kaggle_runtime_start``) and
to run competition commands locally. The login is the Kaggle CLI's own: ``kaggle auth
login``, a ``kaggle.json`` file, or the ``KAGGLE_*`` environment variables — this server
stores none of it.

The Kaggle library prints to standard output, which would corrupt the MCP stream, so
every call into it is made with output captured.
"""

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from .. import config

RUNTIME_SLUG = "gpu-bridge-runtime"
RUNTIME_TITLE = "GPU Bridge Runtime"  # Kaggle derives the slug above from this title

_api = None


class KaggleNotLoggedIn(RuntimeError):
    pass


LOGIN_HELP = (
    "No Kaggle login found on this computer. The user logs in once, in a terminal, with:\n"
    "    gpu-bridge login kaggle\n"
    "(or creates an API token at https://www.kaggle.com/settings and saves it as "
    "~/.kaggle/kaggle.json). Then try again."
)


@contextlib.contextmanager
def _quiet():
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        yield sink


def api():
    """An authenticated Kaggle client, or KaggleNotLoggedIn with what to do."""
    global _api
    if _api is not None:
        return _api
    with _quiet():
        try:
            from kaggle.api.kaggle_api_extended import KaggleApi

            client = KaggleApi()
            client.authenticate()
            user = client.get_config_value("username")
        except (SystemExit, Exception):  # noqa: BLE001 - the library exits when not logged in
            user = None
    if not user:
        raise KaggleNotLoggedIn(LOGIN_HELP)
    _api = client
    return client


def logged_in() -> bool:
    try:
        api()
        return True
    except KaggleNotLoggedIn:
        return False


def username() -> str:
    return api().get_config_value("username")


def runtime_ref() -> str:
    return f"{username()}/{RUNTIME_SLUG}"


def push_runtime(code: str, gpu: bool, competitions: List[str], datasets: List[str],
                 timeout_seconds: int) -> str:
    """Push ``code`` as a private script and start it. Returns the session's page URL."""
    client = api()
    folder = Path(config.STATE_DIR) / "kaggle" / RUNTIME_SLUG
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "runtime.py").write_text(code, encoding="utf-8")
    (folder / "kernel-metadata.json").write_text(json.dumps({
        "id": runtime_ref(),
        "title": RUNTIME_TITLE,
        "code_file": "runtime.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": gpu,
        "enable_internet": True,
        "competition_sources": competitions,
        "dataset_sources": datasets,
        "kernel_sources": [],
        "model_sources": [],
    }, indent=2), encoding="utf-8")
    with _quiet():
        response = client.kernels_push(str(folder), timeout=str(int(timeout_seconds)))
    if getattr(response, "error", None):
        raise RuntimeError(f"Kaggle refused to start the session: {response.error}")
    problems = [f"{label} {values}" for label, values in (
        ("unknown competitions", getattr(response, "invalid_competition_sources", None)),
        ("unknown datasets", getattr(response, "invalid_dataset_sources", None)),
    ) if values]
    if problems:
        raise RuntimeError("Kaggle could not attach the requested data: " + "; ".join(problems)
                           + ". Check the names (and accept the competition rules on kaggle.com).")
    return f"https://www.kaggle.com/code/{runtime_ref()}"


def runtime_status() -> Tuple[str, str]:
    """(status name such as RUNNING / COMPLETE / ERROR, failure message)."""
    with _quiet():
        response = api().kernels_status(runtime_ref())
    status = response.status
    return str(getattr(status, "name", status)).upper(), (response.failure_message or "")


def runtime_logs() -> str:
    with _quiet():
        try:
            return api().kernels_logs(runtime_ref()) or ""
        except Exception:  # noqa: BLE001 - logs are a convenience channel; never fail on them
            return ""


def forward_env() -> dict:
    """Environment variables that log the Kaggle CLI in elsewhere; {} when not logged in here.

    Used to run one Kaggle command on a runtime that has no Kaggle login of its own.
    """
    try:
        values = api().config_values
    except KaggleNotLoggedIn:
        return {}
    if values.get("token"):
        return {"KAGGLE_API_TOKEN": values["token"]}
    if values.get("username") and values.get("key"):
        return {"KAGGLE_USERNAME": values["username"], "KAGGLE_KEY": values["key"]}
    return {}


def cli(args: List[str], timeout: int = 300, cwd: Optional[str] = None) -> str:
    """Run the Kaggle command line on this computer and return what it printed."""
    done = subprocess.run([sys.executable, "-m", "kaggle", *args], capture_output=True,
                          text=True, timeout=timeout, cwd=cwd)
    out = done.stdout.strip()
    if done.stderr.strip():
        out += ("\n" if out else "") + "[stderr] " + done.stderr.strip()
    return out or "(no output)"
