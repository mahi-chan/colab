"""Entrypoint of the interactive Hugging Face runtime. Runs INSIDE the rented machine.

``hf_runtime_start`` ships this file to a Hugging Face Job as its command. It:

1. installs Jupyter if the image lacks it,
2. starts a Jupyter server on the port the Job exposes, and
3. watches for idleness and exits when nothing has happened for a while, which ends
   the Job and stops the billing. Before exiting it uploads the runs directory to a
   private Hub repo so checkpoints are not lost with the machine.

Standard library only: it must run in any image that has Python.
"""

import datetime
import glob
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

PORT = int(os.environ.get("THESIS_PORT", "8888"))
ROOT = os.environ.get("THESIS_ROOT", "/workspace")
IDLE_SECONDS = float(os.environ.get("THESIS_IDLE_MINUTES", "30")) * 60
TOKEN = os.environ.get("JUPYTER_TOKEN", "")
ARCHIVE_REPO = os.environ.get("THESIS_ARCHIVE_REPO", "")
RUNS_DIR = os.path.join(ROOT, "thesis_runs")
CHECK_EVERY = float(os.environ.get("THESIS_WATCH_SECONDS", "30"))


def log(*parts):
    print("[thesis-mcp]", *parts, flush=True)


def ensure_packages():
    wanted = {"jupyter_server": "jupyter_server", "ipykernel": "ipykernel",
              "matplotlib": "matplotlib", "huggingface_hub": "huggingface_hub"}
    missing = []
    for module, package in wanted.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if not missing:
        return
    log("installing", " ".join(missing))
    pip = [sys.executable, "-m", "pip", "install", "-q"]
    if subprocess.run(pip + missing).returncode != 0:
        # system Pythons marked "externally managed" refuse a plain pip install
        subprocess.run(pip + ["--break-system-packages"] + missing, check=True)


def api(path):
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}{sep}no_track_activity=1",
        headers={"Authorization": f"token {TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def background_work_alive():
    """True while a launched run (or a Hub upload) is still running."""
    for pidfile in glob.glob(os.path.join(RUNS_DIR, "*", "*pid")):
        try:
            pid = int(open(pidfile).read().strip())
            stat = open(f"/proc/{pid}/stat").read()
        except (OSError, ValueError):
            continue
        if stat.rsplit(")", 1)[1].split()[0] != "Z":
            return True
    return False


def idle_seconds():
    """Seconds since the runtime last did anything; 0 while it is busy."""
    if background_work_alive():
        return 0.0
    if any(k.get("execution_state") == "busy" for k in api("/api/kernels")):
        return 0.0
    last = api("/api/status")["last_activity"]
    last = datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
    return (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds()


def archive_runs():
    if not (ARCHIVE_REPO and os.environ.get("HF_TOKEN") and os.path.isdir(RUNS_DIR)):
        return
    if not any(files for _, _, files in os.walk(RUNS_DIR)):
        return
    try:
        from huggingface_hub import HfApi

        hub = HfApi()
        hub.create_repo(ARCHIVE_REPO, private=True, exist_ok=True)
        hub.upload_folder(
            folder_path=RUNS_DIR, repo_id=ARCHIVE_REPO,
            path_in_repo=os.environ.get("JOB_ID", "runtime"),
            commit_message="Archive runs before idle shutdown",
        )
        log("archived runs to", ARCHIVE_REPO)
    except Exception as exc:  # never let a failed upload keep a paid machine alive
        log("could not archive runs:", exc)


def main():
    os.makedirs(RUNS_DIR, exist_ok=True)
    ensure_packages()
    server = subprocess.Popen([
        sys.executable, "-m", "jupyter_server",
        "--ServerApp.ip=0.0.0.0", f"--ServerApp.port={PORT}", "--ServerApp.port_retries=0",
        f"--IdentityProvider.token={TOKEN}",
        "--ServerApp.allow_origin=*", "--ServerApp.allow_remote_access=True",
        "--ServerApp.disable_check_xsrf=True",
        "--no-browser", "--allow-root", f"--ServerApp.root_dir={ROOT}",
    ])

    def stop(signum, _frame):
        log("received signal", signum, "- stopping")
        server.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log(f"jupyter starting on port {PORT}, root {ROOT}, "
        f"idle shutdown after {IDLE_SECONDS / 60:g} min")

    while True:
        time.sleep(CHECK_EVERY)
        if server.poll() is not None:
            log("jupyter exited with code", server.returncode)
            sys.exit(server.returncode or 0)
        if IDLE_SECONDS <= 0:
            continue
        try:
            idle = idle_seconds()
        except Exception as exc:  # server still starting, or a transient error
            log("idle check failed:", exc)
            continue
        if idle > IDLE_SECONDS:
            log(f"idle for {idle / 60:.0f} min - shutting down to stop billing")
            archive_runs()
            server.terminate()
            sys.exit(0)


if __name__ == "__main__":
    main()
