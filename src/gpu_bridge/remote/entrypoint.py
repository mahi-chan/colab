"""The program that turns a remote machine into a runtime. Runs ON that machine.

It is started in one of three ways, and behaves the same in all of them:

* Kaggle    - pushed as a script by ``kaggle_runtime_start`` (settings prepended to it);
* Colab     - one pasted line: ``!curl -fsSL <url> | python3 - <pairing code>``;
* Hugging Face - shipped as the command of a Job by ``hf_runtime_start``.

What it does:

1. installs Jupyter if the image lacks it and starts a Jupyter server;
2. unless the platform already exposes the port (Hugging Face), opens a public tunnel
   to it and *announces* the tunnel address, so the user never copies anything back;
3. watches for idleness (or a stop request) and exits, which frees the machine. Before
   an idle exit it uploads the runs folder to a private Hub repo when it can.

Announcing: the address is printed to the log and posted to a rendezvous topic, signed
with the pairing code. The topic name is a hash of the code, so whoever can read the
topic learns neither the code (which is also the Jupyter password) nor can forge an
address that the other side would accept.

Standard library only: it must run in any image that has Python.
"""

import datetime
import glob
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ANNOUNCE_MARKER = "GPU_BRIDGE_ANNOUNCE "
CODE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
DEFAULT_RENDEZVOUS = "https://ntfy.sh"
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"


# -- pairing: shared with the local side (gpu_bridge.connectors.pairing) --------
def topic_for(code):
    """Rendezvous topic for a pairing code. One-way: the topic does not reveal the code."""
    return "gpub-" + hashlib.sha256(("topic:" + code).encode()).hexdigest()[:40]


def sign(code, url):
    return hmac.new(code.encode(), url.encode(), hashlib.sha256).hexdigest()


def announcement(code, url):
    return ANNOUNCE_MARKER + json.dumps({"url": url, "sig": sign(code, url)})


# -- helpers --------------------------------------------------------------------
def log(*parts):
    print("[gpu-bridge]", *parts, flush=True)


def default_root():
    for candidate in ("/content", "/kaggle/working"):
        if os.path.isdir(candidate):
            return candidate
    return "/workspace"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


class Runtime:
    def __init__(self):
        env = os.environ
        self.code = env.get("GPU_BRIDGE_PAIR_CODE", "")
        token = env.get("JUPYTER_TOKEN", "")
        if not self.code and not token and len(sys.argv) > 1 and CODE_PATTERN.match(sys.argv[1]):
            self.code = sys.argv[1]
        # With a pairing code, the code is the Jupyter password. Without one and without a
        # token (someone ran this by hand), make a token and print it at the end.
        self.manual = not self.code and not token
        self.token = self.code or token or secrets.token_hex(16)
        # A tunnel is needed unless the platform exposes the port itself (token given, no code).
        self.tunnel = env.get("GPU_BRIDGE_TUNNEL", "0" if (token and not self.code) else "1") == "1"
        self.port = int(env.get("GPU_BRIDGE_PORT") or (free_port() if self.tunnel else 8888))
        self.root = env.get("GPU_BRIDGE_ROOT") or default_root()
        self.runs_dir = os.path.join(self.root, "gpu_bridge_runs")
        self.stop_file = os.path.join(self.root, ".gpu_bridge_stop")
        # Colab reclaims idle machines itself and stopping early frees nothing there.
        default_idle = "0" if self.root == "/content" else "30"
        self.idle_seconds = float(env.get("GPU_BRIDGE_IDLE_MINUTES", default_idle)) * 60
        self.check_every = float(env.get("GPU_BRIDGE_WATCH_SECONDS", "30"))
        self.archive_repo = env.get("GPU_BRIDGE_ARCHIVE_REPO", "")
        self.rendezvous = env.get("GPU_BRIDGE_RENDEZVOUS_URL", DEFAULT_RENDEZVOUS).rstrip("/")
        self.public_url = env.get("GPU_BRIDGE_PUBLIC_URL", "")
        self.server = None
        self.tunnel_proc = None

    # -- jupyter ------------------------------------------------------------
    def api(self, path):
        sep = "&" if "?" in path else "?"
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}{sep}no_track_activity=1",
            headers={"Authorization": f"token {self.token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)

    def start_jupyter(self):
        os.makedirs(self.runs_dir, exist_ok=True)
        if os.path.exists(self.stop_file):
            os.remove(self.stop_file)
        self.server = subprocess.Popen([
            sys.executable, "-m", "jupyter_server",
            "--ServerApp.ip=0.0.0.0", f"--ServerApp.port={self.port}", "--ServerApp.port_retries=0",
            f"--IdentityProvider.token={self.token}",
            "--ServerApp.allow_origin=*", "--ServerApp.allow_remote_access=True",
            "--ServerApp.disable_check_xsrf=True",
            "--no-browser", "--allow-root", f"--ServerApp.root_dir={self.root}",
        ], stdout=subprocess.DEVNULL if self.tunnel else None,
            stderr=subprocess.DEVNULL if self.tunnel else None)
        for _ in range(120):
            if self.server.poll() is not None:
                raise RuntimeError(f"jupyter exited with code {self.server.returncode}")
            try:
                self.api("/api/status")
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("jupyter did not start within 60 seconds")

    # -- tunnel + announce --------------------------------------------------
    def open_tunnel(self):
        """Expose the Jupyter port on a public https address and return it."""
        if self.public_url:
            return self.public_url
        arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
            platform.machine().lower(), "amd64")
        binary = os.path.join(self.root, ".cloudflared")
        if not os.path.exists(binary):
            log("downloading the tunnel program")
            urllib.request.urlretrieve(CLOUDFLARED_URL.format(arch=arch), binary)
            os.chmod(binary, 0o755)
        tunnel_log = os.path.join(self.root, ".cloudflared.log")
        # Output goes to a file, not a pipe: an unread pipe fills up and stalls the tunnel.
        self.tunnel_proc = subprocess.Popen(
            [binary, "tunnel", "--url", f"http://localhost:{self.port}", "--no-autoupdate"],
            stdout=open(tunnel_log, "w"), stderr=subprocess.STDOUT)
        for _ in range(180):
            found = re.search(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com",
                              open(tunnel_log, errors="replace").read())
            if found:
                return found.group(0)
            if self.tunnel_proc.poll() is not None:
                break
            time.sleep(0.5)
        raise RuntimeError(f"the tunnel did not come up; see {tunnel_log}")

    def announce(self, url):
        """Tell the local side where we are: in the log and on the rendezvous topic."""
        line = announcement(self.code, url)
        print(line, flush=True)
        if not self.rendezvous:
            return
        try:
            req = urllib.request.Request(f"{self.rendezvous}/{topic_for(self.code)}",
                                         data=line.encode(), method="POST")
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as exc:
            log("could not post the address to the rendezvous service:", exc)

    # -- idleness -----------------------------------------------------------
    def background_work_alive(self):
        """True while a launched run (or a Hub upload) is still running."""
        for pidfile in glob.glob(os.path.join(self.runs_dir, "*", "*pid")):
            try:
                pid = int(open(pidfile).read().strip())
                stat = open(f"/proc/{pid}/stat").read()
            except (OSError, ValueError):
                continue
            if stat.rsplit(")", 1)[1].split()[0] != "Z":
                return True
        return False

    def idle_for(self):
        """Seconds since the runtime last did anything; 0 while it is busy."""
        if self.background_work_alive():
            return 0.0
        if any(k.get("execution_state") == "busy" for k in self.api("/api/kernels")):
            return 0.0
        last = self.api("/api/status")["last_activity"]
        last = datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds()

    def archive_runs(self):
        if not (self.archive_repo and os.environ.get("HF_TOKEN") and os.path.isdir(self.runs_dir)):
            return
        if not any(files for _, _, files in os.walk(self.runs_dir)):
            return
        try:
            from huggingface_hub import HfApi

            hub = HfApi()
            hub.create_repo(self.archive_repo, private=True, exist_ok=True)
            hub.upload_folder(
                folder_path=self.runs_dir, repo_id=self.archive_repo,
                path_in_repo=os.environ.get("JOB_ID", "runtime"),
                commit_message="Archive runs before idle shutdown",
            )
            log("archived runs to", self.archive_repo)
        except Exception as exc:  # never let a failed upload keep a machine alive
            log("could not archive runs:", exc)

    def shutdown(self, code=0):
        for proc in (self.tunnel_proc, self.server):
            if proc is not None and proc.poll() is None:
                proc.terminate()
        sys.exit(code)

    # -- main loop ----------------------------------------------------------
    def run(self):
        ensure_packages()
        self.start_jupyter()

        def on_signal(signum, _frame):
            log("received signal", signum, "- stopping")
            self.shutdown(0)

        signal.signal(signal.SIGTERM, on_signal)
        signal.signal(signal.SIGINT, on_signal)

        url = ""
        if self.tunnel:
            url = self.open_tunnel()
            if self.code:
                self.announce(url)
                log("connected. Tell the assistant it is running; leave this running.")
            if self.manual:
                log("runtime is up. Give these two values to the assistant:")
                print(f'  JUPYTER_URL="{url}"\n  JUPYTER_TOKEN="{self.token}"', flush=True)
        idle_note = (f"idle shutdown after {self.idle_seconds / 60:g} min"
                     if self.idle_seconds > 0 else "no idle shutdown")
        log(f"jupyter on port {self.port}, root {self.root}, {idle_note}")

        last_announce = time.time()
        while True:
            time.sleep(self.check_every)
            if self.server.poll() is not None:
                log("jupyter exited with code", self.server.returncode)
                self.shutdown(self.server.returncode or 0)
            if os.path.exists(self.stop_file):
                log("stop requested - shutting down")
                self.shutdown(0)
            if self.tunnel_proc is not None and self.tunnel_proc.poll() is not None:
                log("the tunnel exited - shutting down")
                self.shutdown(1)
            if self.code and url and time.time() - last_announce > 900:
                self.announce(url)  # keep the address findable for a late or returning client
                last_announce = time.time()
            if self.idle_seconds <= 0:
                continue
            try:
                idle = self.idle_for()
            except Exception as exc:  # a transient error must not end the session
                log("idle check failed:", exc)
                continue
            if idle > self.idle_seconds:
                log(f"idle for {idle / 60:.0f} min - shutting down to free the machine")
                self.archive_runs()
                self.shutdown(0)


def main():
    try:
        Runtime().run()
    except RuntimeError as exc:
        log("failed:", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
