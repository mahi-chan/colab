"""Configuration, read from environment variables at process start.

All secrets/URLs come from the environment so nothing sensitive is ever
committed. In Claude Code these are supplied via ``.mcp.json`` (which expands
``${VAR}`` from your shell) or via ``claude mcp add ... -e VAR=value``.
"""

import os

# Where the local run registry + remembered kernel id are stored (user's machine).
STATE_DIR = os.environ.get("THESIS_STATE_DIR", os.path.expanduser("~/.thesis-mcp"))

# Connection to the Jupyter server running inside the Colab/Kaggle VM.
JUPYTER_URL = os.environ.get("JUPYTER_URL", "").rstrip("/")
JUPYTER_TOKEN = os.environ.get("JUPYTER_TOKEN", "")

# Optional overrides. When empty these are auto-detected on connect
# (/content for Colab, /kaggle/working for Kaggle).
CONTENTS_ROOT = os.environ.get("THESIS_CONTENTS_ROOT", "")
RUN_ROOT = os.environ.get("THESIS_RUN_ROOT", "")

# Default timeout (seconds) for a single synchronous code execution.
EXEC_TIMEOUT = int(os.environ.get("THESIS_EXEC_TIMEOUT", "120"))
