"""Start a Colab or Kaggle session and pair with it, with as little manual work as possible.

* Kaggle — ``kaggle_runtime_start`` starts a GPU session through the user's Kaggle login.
  Nothing is done in the browser.
* Colab — Google offers no way to start a session from outside, so the user opens a
  notebook and runs one pasted line. Nothing is copied back.

Either way the session announces its own address (see ``connectors/pairing.py``) and
``connect_runtime`` picks it up.
"""

import base64
import json
import time
import zlib

import requests

from .. import config
from .. import runtime_state as rs
from ..connectors import kaggle_api, pairing
from ..remote import entrypoint as remote

KAGGLE_ENDED = ("COMPLETE", "ERROR", "CANCEL_REQUESTED", "CANCEL_ACKNOWLEDGED")


def pending() -> dict:
    """The session we started and have not connected to yet (empty if none)."""
    pair = rs.store.get_section("pairing")
    return pair if pair.get("code") and not pair.get("url") else {}


def _kaggle_script(code: str, idle_minutes: int) -> str:
    """The runtime program with its settings in front, as one script for Kaggle to run."""
    settings = {
        "GPU_BRIDGE_PAIR_CODE": code,
        "GPU_BRIDGE_IDLE_MINUTES": str(int(idle_minutes)),
        "GPU_BRIDGE_RENDEZVOUS_URL": config.RENDEZVOUS_URL,
    }
    return (f"import os\nos.environ.update({json.dumps(settings)})\n\n"
            + pairing.entrypoint_source()
            + '\nif __name__ != "__main__":\n    main()\n')


def _colab_line(code: str) -> str:
    """One line for a Colab cell: the short download form when GitHub serves the current
    program, otherwise a self-contained line that needs nothing from the network."""
    try:
        served = requests.get(pairing.entrypoint_url(), timeout=10)
        if served.status_code == 200 and remote.ANNOUNCE_MARKER in served.text:
            line = pairing.colab_command(code)
            if config.RENDEZVOUS_URL != remote.DEFAULT_RENDEZVOUS:
                line = line.replace("| python3", f"| GPU_BRIDGE_RENDEZVOUS_URL={config.RENDEZVOUS_URL} python3")
            return line
    except requests.RequestException:
        pass
    blob = base64.b64encode(zlib.compress(pairing.entrypoint_source().encode(), 9)).decode()
    return ("import os,base64,zlib;os.environ.update(GPU_BRIDGE_PAIR_CODE=%r,GPU_BRIDGE_RENDEZVOUS_URL=%r);"
            "exec(compile(zlib.decompress(base64.b64decode(%r)),'entrypoint.py','exec'))"
            % (code, config.RENDEZVOUS_URL, blob))


def find_address(pair: dict) -> str:
    """Where the paired session says it is, or "" if it has not announced itself yet."""
    url = pairing.from_rendezvous(pair["code"])
    if not url and pair.get("platform") == "kaggle":
        url = pairing.find_announcement(kaggle_api.runtime_logs(), pair["code"])
    return url or ""


def connect_pending(connect_impl, wait_seconds: int) -> str:
    """Wait for the session we started to announce itself, then attach to it."""
    pair = pending()
    platform = pair["platform"]
    deadline = time.time() + max(0, wait_seconds)
    while True:
        url = find_address(pair)
        if url:
            rs.jupyter.configure(url, pair["code"])
            if rs.jupyter.ping():
                rs.store.set_section("pairing", {**pair, "url": url})
                return connect_impl(pair_code=pair["code"], platform=platform)
        if platform == "kaggle":
            status, failure = kaggle_api.runtime_status()
            if status in KAGGLE_ENDED:
                rs.store.set_section("pairing", {})
                tail = "\n".join(kaggle_api.runtime_logs().splitlines()[-15:])
                return (f"The Kaggle session ended before connecting: {status}. {failure}\n{tail}\n"
                        "Common causes: the account is not phone-verified (needed for internet "
                        "and GPU), or the weekly GPU quota is used up. Start again with "
                        "kaggle_runtime_start (try gpu=False to check).").strip()
        if time.time() >= deadline:
            if platform == "kaggle":
                return ("Not ready yet: Kaggle is still starting the session (this takes one to "
                        f"three minutes). Call connect_runtime again shortly. Page: {pair.get('page')}")
            return ("Not connected yet: no session has announced itself. Ask the user whether the "
                    "line is running in Colab (it prints 'connected' when ready), then call "
                    "connect_runtime again.")
        time.sleep(4)


def register(mcp, connect_impl):
    @mcp.tool()
    def kaggle_runtime_start(gpu: bool = True, competition: str = "", datasets: str = "",
                             idle_minutes: int = 30, max_hours: float = 6) -> str:
        """Start a Kaggle GPU session without the browser, using the user's Kaggle login.

        Returns at once; then call connect_runtime (Kaggle needs a minute or two). After
        that every runtime tool works on the Kaggle machine. It uses the account's free
        weekly GPU hours until runtime_stop, ``max_hours``, or ``idle_minutes`` with
        nothing running.

        competition: a competition slug to attach; its data appears under /kaggle/input/.
                     (The user must have accepted the competition rules on kaggle.com.)
        datasets: comma-separated "owner/dataset" names to attach under /kaggle/input/.
        gpu: False starts a CPU session, which does not use GPU quota.
        """
        try:
            current = pending() or rs.store.get_section("pairing")
            if current.get("platform") == "kaggle":
                try:
                    status = kaggle_api.runtime_status()[0]
                except kaggle_api.KaggleNotLoggedIn:
                    raise
                except Exception:  # noqa: BLE001 - e.g. the notebook was deleted on Kaggle
                    status = ""
                if status in ("RUNNING", "QUEUED"):
                    return ("A Kaggle session started here is already running. Call connect_runtime "
                            "to use it, or runtime_stop first.")
            code = pairing.new_code()
            page = kaggle_api.push_runtime(
                _kaggle_script(code, idle_minutes), gpu=gpu,
                competitions=[c.strip() for c in competition.split(",") if c.strip()],
                datasets=[d.strip() for d in datasets.split(",") if d.strip()],
                timeout_seconds=int(max_hours * 3600),
            )
        except kaggle_api.KaggleNotLoggedIn as exc:
            return str(exc)
        except RuntimeError as exc:
            return str(exc)
        rs.store.set_section("pairing", {"platform": "kaggle", "code": code, "page": page})
        return (f"Started a Kaggle {'GPU' if gpu else 'CPU'} session ({page}).\n"
                "Call connect_runtime in about a minute; it re-checks until the session is up.")

    @mcp.tool()
    def colab_runtime_start() -> str:
        """Prepare a Google Colab session. Returns one line for the user to run in Colab.

        Google does not let a program start a Colab session, so the user does two things:
        open a notebook and run the line. Nothing is copied back: when the line is
        running, call connect_runtime and the session is found automatically.
        Show the user the steps exactly as returned.
        """
        code = pairing.new_code()
        line = _colab_line(code)
        rs.store.set_section("pairing", {"platform": "colab", "code": code})
        return ("Ask the user to do this in their browser:\n"
                "1. Open https://colab.new  (a new Colab notebook)\n"
                "2. Runtime > Change runtime type > T4 GPU > Save\n"
                "3. Paste this single line into the first cell and run it:\n\n"
                f"{line}\n\n"
                "The cell keeps running; that is expected. When it prints 'connected', the "
                "user tells you, and you call connect_runtime (no arguments).")

    @mcp.tool()
    def runtime_stop() -> str:
        """End the Colab/Kaggle session started with colab_runtime_start / kaggle_runtime_start.

        Download or push results first (save_checkpoint / hf_push_run). On Kaggle this
        stops the GPU-hours clock, and the files in /kaggle/working stay on Kaggle as the
        notebook's output. (A Hugging Face machine is stopped with hf_runtime_stop.)
        """
        saved = rs.store.get_kernel()
        pair = rs.store.get_section("pairing")
        if not saved.get("pair_code"):
            if pair.get("platform") == "kaggle":
                rs.store.set_section("pairing", {})
                return ("The Kaggle session was never connected, so it cannot be told to stop from "
                        f"here. Stop it on its page ({pair.get('page')}), or it ends by itself "
                        "after the idle time.")
            return "No Colab/Kaggle session started from here is connected."
        stop_file = rs.contents_root().rstrip("/") + "/.gpu_bridge_stop"
        result = rs.jupyter.execute(f"open({stop_file!r}, 'w').close(); print('stop requested')",
                                    timeout=30)
        platform = saved.get("platform", "session")
        rs.store.set_section("pairing", {})
        rs.store.set_kernel()
        rs.jupyter.disconnect()
        if result.error:
            return f"Could not reach the {platform} session to stop it (it may already be gone)."
        note = (" Files in /kaggle/working are kept on Kaggle as the notebook's output."
                if platform == "kaggle" else " The Colab cell will finish; close the tab to release the GPU.")
        return f"Stopping the {platform} session; it shuts down within a minute." + note
