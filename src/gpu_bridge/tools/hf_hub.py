"""Hugging Face Hub and Spaces tools.

The Hub is the durable home for models, datasets and checkpoints: remote machines
are temporary, a Hub repo is not. Spaces tools manage a GPU Space you rent by the
hour (connect to a JupyterLab Space with ``connect_runtime(..., hf_auth=True)``).
"""

import os
import posixpath

from huggingface_hub import SpaceHardware

from .. import runtime_state as rs
from ..connectors import hf
from .core import is_job
from .hf_jobs import hf_errors

# Runs on the runtime, as a background process, to upload a run directory to the Hub.
PUSH_SCRIPT = '''\
import sys
from huggingface_hub import HfApi
run_dir, repo_id, private = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
hub = HfApi()
hub.create_repo(repo_id, private=private, exist_ok=True)
hub.upload_folder(
    folder_path=run_dir, repo_id=repo_id,
    ignore_patterns=["pid", "*.pid", "hub_push.*", "_hub_push.py", "_*.png", "checkpoints_bundle.zip"],
    commit_message="Upload run from gpu-bridge",
)
print("PUSH_DONE https://huggingface.co/" + repo_id)
'''


def _space_line(space_id: str, runtime) -> str:
    stage = str(getattr(runtime.stage, "value", runtime.stage))
    hardware = str(getattr(runtime.hardware, "value", runtime.hardware) or "none")
    requested = str(getattr(runtime.requested_hardware, "value", runtime.requested_hardware) or "")
    text = f"{space_id}: {stage} on {hardware}"
    if requested and requested != hardware:
        text += f" (switching to {requested})"
    if runtime.sleep_time:
        text += f", sleeps after {runtime.sleep_time // 60} idle minutes"
    return text


def register(mcp):
    @mcp.tool()
    @hf_errors
    def hf_whoami() -> str:
        """Check the Hugging Face login: who the token belongs to and what it may do."""
        me = hf.api().whoami(token=hf.token())
        orgs = ", ".join(o.get("name", "") for o in me.get("orgs", [])) or "-"
        role = (me.get("auth", {}).get("accessToken", {}) or {}).get("role", "?")
        can_pay = me.get("canPay")
        billing = {True: "yes", False: "no — add a payment method or credits to rent machines"}.get(
            can_pay, "unknown")
        return (f"Logged in to Hugging Face as {me.get('name')} (token role: {role}).\n"
                f"Organizations: {orgs}\nCan pay for compute: {billing}")

    @mcp.tool()
    @hf_errors
    def hf_search(query: str, kind: str = "model", limit: int = 10) -> str:
        """Search the Hugging Face Hub for models or datasets, most downloaded first.

        kind: "model" or "dataset".
        """
        if kind not in ("model", "dataset"):
            return "kind must be 'model' or 'dataset'."
        find = hf.api().list_models if kind == "model" else hf.api().list_datasets
        hits = find(search=query, sort="downloads", limit=int(limit))
        lines = [f"- {h.id}  (downloads {h.downloads or 0}, likes {h.likes or 0}"
                 + (", gated" if getattr(h, "gated", False) else "") + ")" for h in hits]
        return "\n".join(lines) or f"No {kind}s match {query!r}."

    @mcp.tool()
    @hf_errors
    def hf_upload(local_path: str, repo_id: str, repo_type: str = "model",
                  path_in_repo: str = "", private: bool = True) -> str:
        """Upload a local file or folder to a Hub repo (created if missing, private by default).

        repo_id: "<user>/<name>". repo_type: "model", "dataset" or "space".
        """
        if not os.path.exists(local_path):
            return f"No such local path: {local_path}"
        token = hf.token()
        hf.api().create_repo(repo_id, repo_type=repo_type, private=private, exist_ok=True, token=token)
        if os.path.isdir(local_path):
            hf.api().upload_folder(folder_path=local_path, repo_id=repo_id, repo_type=repo_type,
                                   path_in_repo=path_in_repo or None, token=token)
        else:
            hf.api().upload_file(path_or_fileobj=local_path, repo_id=repo_id, repo_type=repo_type,
                                 path_in_repo=path_in_repo or os.path.basename(local_path),
                                 token=token)
        prefix = {"model": "", "dataset": "datasets/", "space": "spaces/"}.get(repo_type, "")
        return f"Uploaded {local_path} -> https://huggingface.co/{prefix}{repo_id}"

    @mcp.tool()
    @hf_errors
    def hf_download(repo_id: str, local_dir: str, filename: str = "",
                    repo_type: str = "model") -> str:
        """Download one file (or, with no filename, a whole repo) from the Hub to the local machine."""
        token = hf.token()
        if filename:
            path = hf.api().hf_hub_download(repo_id, filename, repo_type=repo_type,
                                            local_dir=local_dir, token=token)
        else:
            path = hf.api().snapshot_download(repo_id, repo_type=repo_type,
                                              local_dir=local_dir, token=token)
        return f"Downloaded {repo_id} -> {path}"

    @mcp.tool()
    @hf_errors
    def hf_push_run(run_name: str, repo_id: str = "", private: bool = True) -> str:
        """Upload a run's folder (checkpoints, metrics, log, script) from the runtime to the Hub.

        The upload goes straight from the remote machine, in the background, so large
        checkpoints never pass through this computer. Call it again to check progress.
        It uses this computer's Hugging Face login for that one upload; the token is not
        kept on the runtime.

        repo_id: defaults to "<your username>/<run_name>".
        """
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        if is_job(run):
            return (f"'{run_name}' ran as a Hugging Face job; what it saved is already at "
                    f"https://huggingface.co/{run['hub_repo']}")
        repo_id = repo_id or f"{hf.username()}/{run_name}"
        rd = run["dir"]
        try:
            login = {"HF_TOKEN": hf.token()}
        except hf.HfNotLoggedIn:
            login = {}  # the runtime may have its own login (a Hugging Face machine does)
        rs.jupyter.upload_bytes(rs.to_rel(posixpath.join(rd, "_hub_push.py")), PUSH_SCRIPT.encode())
        code = (
            "import os, subprocess, sys, time\n"
            f"rd = {rd!r}\n"
            "log, pidf = os.path.join(rd, 'hub_push.log'), os.path.join(rd, 'hub_push.pid')\n"
            "def alive():\n"
            "    try:\n"
            "        pid = int(open(pidf).read())\n"
            "        try:\n            os.waitpid(pid, os.WNOHANG)\n        except OSError:\n            pass\n"
            "        return open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()[0] != 'Z'\n"
            "    except (OSError, ValueError):\n        return False\n"
            "if alive():\n    print('STATE uploading')\n"
            "else:\n"
            "    try:\n        import huggingface_hub\n"
            "    except ImportError:\n"
            "        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'huggingface_hub'])\n"
            "        import huggingface_hub\n"
            f"    env = {{**os.environ, **{login!r}}}\n"
            "    if not (env.get('HF_TOKEN') or huggingface_hub.get_token()):\n        print('STATE no_token')\n"
            "    else:\n"
            f"        p = subprocess.Popen([sys.executable, '_hub_push.py', rd, {repo_id!r}, "
            f"{'1' if private else '0'!r}], cwd=rd, stdout=open(log, 'w'), "
            "stderr=subprocess.STDOUT, start_new_session=True, env=env)\n"
            "        open(pidf, 'w').write(str(p.pid))\n"
            "        print('STATE started')\n"
            "for _ in range(40):\n"
            "    if not alive():\n        break\n"
            "    time.sleep(1)\n"
            "print('ALIVE', int(alive()))\n"
            "if os.path.exists(log):\n"
            "    print(chr(10).join(open(log, errors='replace').read().splitlines()[-8:]))\n"
        )
        # the code carries the login, so keep it out of the kernel's history
        res = rs.jupyter.execute(code, timeout=120, store_history=False)
        out = res.text
        if "STATE no_token" in out:
            return ("No Hugging Face login is available, so nothing was uploaded. Log in on this "
                    "computer (see setup_guide('huggingface')) and call hf_push_run again, or "
                    "use save_checkpoint to download the results instead.")
        if "PUSH_DONE" in out:
            return f"Pushed run '{run_name}' to https://huggingface.co/{repo_id}"
        if "ALIVE 1" in out:
            return (f"Uploading run '{run_name}' to {repo_id} in the background; "
                    f"call hf_push_run('{run_name}') again to check.\n{out}")
        return f"Upload did not finish cleanly:\n{out}"

    # -- Spaces -------------------------------------------------------------
    @mcp.tool()
    @hf_errors
    def hf_space_status(space_id: str) -> str:
        """Show a Space's state, hardware and URL. space_id is "<user>/<space>"."""
        token = hf.token()
        runtime = hf.api().get_space_runtime(space_id, token=token)
        info = hf.api().space_info(space_id, token=token)
        host = info.host or (f"https://{info.subdomain}.hf.space" if info.subdomain else "?")
        return f"{_space_line(space_id, runtime)}\nurl: {host}"

    @mcp.tool()
    @hf_errors
    def hf_space_hardware(space_id: str, hardware: str, sleep_minutes: int = 0) -> str:
        """Change a Space's hardware (e.g. "t4-small", "a10g-small", or "cpu-basic" for free).

        Paid hardware is billed per minute while the Space runs. sleep_minutes > 0 puts
        the Space to sleep after that long without visitors, which pauses the billing.
        """
        valid = [h.value for h in SpaceHardware]
        if hardware not in valid:
            return f"Unknown hardware {hardware!r}. Choose one of: {', '.join(valid)}"
        runtime = hf.api().request_space_hardware(
            space_id, hardware, sleep_time=sleep_minutes * 60 if sleep_minutes > 0 else None,
            token=hf.token())
        return _space_line(space_id, runtime)

    @mcp.tool()
    @hf_errors
    def hf_space_pause(space_id: str) -> str:
        """Pause a Space: it stops running and stops billing until restarted."""
        return _space_line(space_id, hf.api().pause_space(space_id, token=hf.token()))

    @mcp.tool()
    @hf_errors
    def hf_space_restart(space_id: str) -> str:
        """Restart (or wake) a Space. On paid hardware, billing resumes."""
        return _space_line(space_id, hf.api().restart_space(space_id, token=hf.token()))
