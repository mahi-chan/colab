"""Pairing: how a Colab/Kaggle session that just started finds its way back to us.

We make a random pairing code and hand it to the remote machine (inside the script we
push to Kaggle, or in the one line the user pastes into Colab). The remote program
starts Jupyter with that code as its password, opens a tunnel, and *announces* the
tunnel address, signed with the code. We look for the announcement in two places:

* the rendezvous topic (a public relay; the topic name is a hash of the code), and
* for Kaggle, the session's own log, read through the Kaggle API.

An address is only accepted if its signature matches, so neither the relay nor anyone
reading it can send us somewhere else or learn the code.
"""

import hmac
import json
import secrets
from pathlib import Path
from typing import Optional

import requests

from .. import config
from ..remote import entrypoint as remote

ENTRYPOINT_PATH = Path(remote.__file__)


def new_code() -> str:
    return secrets.token_hex(16)


def find_announcement(text: str, code: str) -> Optional[str]:
    """The most recent correctly signed address in ``text``, or None."""
    found = None
    for chunk in text.split(remote.ANNOUNCE_MARKER)[1:]:
        try:
            data, _ = json.JSONDecoder().raw_decode(chunk.replace('\\"', '"'))
            url, sig = data["url"], data["sig"]
        except (ValueError, KeyError, TypeError):
            continue
        if isinstance(url, str) and isinstance(sig, str) and hmac.compare_digest(sig, remote.sign(code, url)):
            found = url
    return found


def from_rendezvous(code: str) -> Optional[str]:
    """Ask the rendezvous service for the address announced for this code."""
    try:
        response = requests.get(f"{config.RENDEZVOUS_URL}/{remote.topic_for(code)}/json",
                                params={"poll": "1", "since": "12h"}, timeout=15)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    messages = []
    for line in response.text.splitlines():
        try:
            messages.append(json.loads(line).get("message", ""))
        except ValueError:
            continue
    return find_announcement("\n".join(m for m in messages if isinstance(m, str)), code)


def entrypoint_source() -> str:
    return ENTRYPOINT_PATH.read_text(encoding="utf-8")


def entrypoint_url() -> str:
    return (f"https://raw.githubusercontent.com/{config.REPO_SLUG}/{config.REPO_BRANCH}"
            "/src/thesis_mcp/remote/entrypoint.py")


def colab_command(code: str) -> str:
    """The one line to run in a Colab cell. Nothing has to be copied back afterwards."""
    return f"!curl -fsSL {entrypoint_url()} | python3 - {code}"
