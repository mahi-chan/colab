"""Process-wide singletons shared by every tool module.

Kept in one place so the Jupyter connection and the run registry are the same
objects across all tools, and so a fresh process re-attaches to a still-running
kernel that a previous session (before ``/clear``) left behind.
"""

import posixpath

from . import config
from .connectors.jupyter import JupyterClient
from .connectors.store import RunStore

store = RunStore(config.STATE_DIR)

# Re-hydrate the connection remembered from a previous session. The token is
# never persisted (secrets stay in env), so it always comes from the environment.
_saved = store.get_kernel()
# A freshly exported JUPYTER_URL (new VM / new tunnel) must win over the remembered
# one; the remembered kernel id is only meaningful for the URL it was saved with.
_url = config.JUPYTER_URL or _saved.get("url") or ""
_same_server = _url.rstrip("/") == (_saved.get("url") or "").rstrip("/")
jupyter = JupyterClient(
    url=_url,
    token=config.JUPYTER_TOKEN,
    kernel_id=_saved.get("kernel_id", "") if _same_server else "",
)


def contents_root() -> str:
    """Root the Jupyter server serves files from (Contents API paths are relative to it)."""
    return config.CONTENTS_ROOT or store.get_kernel().get("contents_root") or "/content"


def run_root() -> str:
    """Absolute directory on the runtime where launched runs live."""
    return (
        config.RUN_ROOT
        or store.get_kernel().get("run_root")
        or posixpath.join(contents_root(), "thesis_runs")
    )


def to_rel(abs_path: str) -> str:
    """Convert an absolute runtime path to a Contents-API path (relative to contents_root)."""
    root = contents_root().rstrip("/")
    if abs_path.startswith(root + "/"):
        return abs_path[len(root) + 1:]
    return abs_path.lstrip("/")
