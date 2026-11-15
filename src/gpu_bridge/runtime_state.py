"""Process-wide singletons shared by every tool module.

Kept in one place so the Jupyter connection and the run registry are the same
objects across all tools, and so a fresh process re-attaches to a still-running
kernel that a previous session (before ``/clear``) left behind.
"""

import posixpath

from . import config
from .connectors import hf
from .connectors.jupyter import JupyterClient
from .connectors.store import RunStore

store = RunStore(config.STATE_DIR)


def _rehydrate() -> JupyterClient:
    """Rebuild the connection remembered from a previous session.

    Account credentials are never persisted: tokens come from the environment, or for a
    Hugging Face runtime we started are re-derived from the HF token. The one thing kept
    is the one-time pairing code of a Colab/Kaggle session, which dies with that session.
    """
    saved = store.get_kernel()
    saved_url = (saved.get("url") or "").rstrip("/")
    # A freshly exported JUPYTER_URL (new VM / new tunnel) must win over the remembered
    # one; the remembered kernel id and auth mode only apply to the URL they were saved with.
    url = config.JUPYTER_URL or saved_url
    if not url or url != saved_url:
        return JupyterClient(url=url, token=config.JUPYTER_TOKEN)

    # A session we paired with uses its pairing code as the Jupyter password.
    token, bearer = saved.get("pair_code") or config.JUPYTER_TOKEN, ""
    if saved.get("auth") == "hf":
        try:
            bearer = hf.token()
            if saved.get("nonce"):
                token = hf.jupyter_token(saved["nonce"])
        except hf.HfNotLoggedIn:
            pass  # surfaces as a clear error on the first tool call that needs it
    return JupyterClient(url=url, token=token, kernel_id=saved.get("kernel_id", ""), bearer=bearer)


jupyter = _rehydrate()


def contents_root() -> str:
    """Root the Jupyter server serves files from (Contents API paths are relative to it)."""
    return config.CONTENTS_ROOT or store.get_kernel().get("contents_root") or "/content"


def run_root() -> str:
    """Absolute directory on the runtime where launched runs live."""
    return (
        config.RUN_ROOT
        or store.get_kernel().get("run_root")
        or posixpath.join(contents_root(), "gpu_bridge_runs")
    )


def to_rel(abs_path: str) -> str:
    """Convert an absolute runtime path to a Contents-API path (relative to contents_root)."""
    root = contents_root().rstrip("/")
    if abs_path.startswith(root + "/"):
        return abs_path[len(root) + 1:]
    return abs_path.lstrip("/")
