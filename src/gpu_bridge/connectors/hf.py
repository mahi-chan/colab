"""Hugging Face access: one shared ``HfApi`` client plus token helpers.

The token is never stored by this server. ``huggingface_hub`` finds it itself, in
the ``HF_TOKEN`` environment variable or the login saved by ``hf auth login``.
"""

import hashlib
import hmac
from typing import Optional

from huggingface_hub import HfApi, get_token

_api: Optional[HfApi] = None


class HfNotLoggedIn(RuntimeError):
    pass


def api() -> HfApi:
    global _api
    if _api is None:
        _api = HfApi(library_name="gpu-bridge")
    return _api


def token() -> str:
    """The user's Hugging Face token, or a clear error telling them how to provide one."""
    tok = get_token()
    if not tok:
        raise HfNotLoggedIn(
            "No Hugging Face token found. The user creates one with write access at "
            "https://huggingface.co/settings/tokens and logs in once, in a terminal, with: "
            "gpu-bridge login huggingface"
        )
    return tok


def username() -> str:
    return api().whoami(token=token(), cache=True)["name"]


def jupyter_token(nonce: str) -> str:
    """Jupyter token for a runtime we started, derived from the HF token and a nonce.

    Deriving it (instead of saving it) means no secret is written to disk, and a
    new session can rebuild it from the nonce remembered in the state file.
    """
    return hmac.new(token().encode(), f"gpu-bridge:{nonce}".encode(), hashlib.sha256).hexdigest()
