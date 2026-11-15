"""Configuration, read from environment variables at process start.

All secrets/URLs come from the environment so nothing sensitive is ever
committed. In Claude Code these are supplied via ``.mcp.json`` (which expands
``${VAR}`` from your shell) or via ``claude mcp add ... -e VAR=value``.
"""

import os

_KNOWN_VARS = (
    "JUPYTER_URL", "JUPYTER_TOKEN", "HF_TOKEN",
    "GPU_BRIDGE_STATE_DIR", "GPU_BRIDGE_CONTENTS_ROOT", "GPU_BRIDGE_RUN_ROOT", "GPU_BRIDGE_HF_IMAGE",
    "KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_API_TOKEN",
)

# When a variable referenced in .mcp.json is not set in the shell, the literal text
# "${VAR}" can reach us instead of a value. Drop those so they read as "not set"
# (this must run before huggingface_hub looks at HF_TOKEN).
for _name in _KNOWN_VARS:
    if os.environ.get(_name, "").startswith("${"):
        del os.environ[_name]

# Where the local run registry + remembered kernel id are stored (user's machine).
STATE_DIR = os.environ.get("GPU_BRIDGE_STATE_DIR") or os.path.expanduser("~/.gpu-bridge")

# Connection to the Jupyter server running inside the Colab/Kaggle VM.
JUPYTER_URL = os.environ.get("JUPYTER_URL", "").rstrip("/")
JUPYTER_TOKEN = os.environ.get("JUPYTER_TOKEN", "")

# Optional overrides. When empty these are auto-detected on connect
# (/content for Colab, /kaggle/working for Kaggle, the server root elsewhere).
CONTENTS_ROOT = os.environ.get("GPU_BRIDGE_CONTENTS_ROOT", "")
RUN_ROOT = os.environ.get("GPU_BRIDGE_RUN_ROOT", "")

# Docker image for the interactive Hugging Face runtime (hf_runtime_start).
HF_RUNTIME_IMAGE = (os.environ.get("GPU_BRIDGE_HF_IMAGE")
                    or "pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime")

# Where this project lives on GitHub. The Colab one-liner downloads the runtime program
# from here; change these two when the project moves (for example after merging to main).
REPO_SLUG = os.environ.get("GPU_BRIDGE_REPO_SLUG") or "mahi-chan/gpu-bridge"
REPO_BRANCH = os.environ.get("GPU_BRIDGE_BRANCH") or "main"

# Service a freshly started Colab/Kaggle session uses to tell this computer its address.
# Any ntfy-compatible server works; only a signed tunnel address ever passes through it.
RENDEZVOUS_URL = (os.environ.get("GPU_BRIDGE_RENDEZVOUS_URL") or "https://ntfy.sh").rstrip("/")
