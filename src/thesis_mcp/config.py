"""Configuration, read from environment variables at process start.

All secrets/URLs come from the environment so nothing sensitive is ever
committed. In Claude Code these are supplied via ``.mcp.json`` (which expands
``${VAR}`` from your shell) or via ``claude mcp add ... -e VAR=value``.
"""

import os

_KNOWN_VARS = (
    "JUPYTER_URL", "JUPYTER_TOKEN", "HF_TOKEN",
    "THESIS_STATE_DIR", "THESIS_CONTENTS_ROOT", "THESIS_RUN_ROOT", "THESIS_HF_IMAGE",
)

# When a variable referenced in .mcp.json is not set in the shell, the literal text
# "${VAR}" can reach us instead of a value. Drop those so they read as "not set"
# (this must run before huggingface_hub looks at HF_TOKEN).
for _name in _KNOWN_VARS:
    if os.environ.get(_name, "").startswith("${"):
        del os.environ[_name]

# Where the local run registry + remembered kernel id are stored (user's machine).
STATE_DIR = os.environ.get("THESIS_STATE_DIR") or os.path.expanduser("~/.thesis-mcp")

# Connection to the Jupyter server running inside the Colab/Kaggle VM.
JUPYTER_URL = os.environ.get("JUPYTER_URL", "").rstrip("/")
JUPYTER_TOKEN = os.environ.get("JUPYTER_TOKEN", "")

# Optional overrides. When empty these are auto-detected on connect
# (/content for Colab, /kaggle/working for Kaggle, the server root elsewhere).
CONTENTS_ROOT = os.environ.get("THESIS_CONTENTS_ROOT", "")
RUN_ROOT = os.environ.get("THESIS_RUN_ROOT", "")

# Docker image for the interactive Hugging Face runtime (hf_runtime_start).
HF_RUNTIME_IMAGE = (os.environ.get("THESIS_HF_IMAGE")
                    or "pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime")
