# =====================================================================
# thesis-mcp  ·  KAGGLE BOOTSTRAP
# Paste into a Kaggle Notebook and RUN it.
#   1. Notebook settings: Accelerator = GPU, and Internet = ON.
#   2. Run this cell and leave it running.
#   3. Copy the printed JUPYTER_URL / JUPYTER_TOKEN to your local machine.
# Kaggle credentials are already configured inside Kaggle notebooks, so
# cv_load_dataset / kaggle_* work out of the box here.
# =====================================================================

import os, re, secrets, shutil, subprocess, time, urllib.request

TOKEN = secrets.token_hex(16)
PORT = 8888
ROOT = "/kaggle/working"

subprocess.run("pip -q install jupyter_server".split(), check=False)

CF = f"{ROOT}/cloudflared"
if not os.path.exists(CF):
    urllib.request.urlretrieve(
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
        CF,
    )
    os.chmod(CF, 0o755)

_JUPYTER = subprocess.Popen(
    [
        "jupyter", "server",
        "--ServerApp.ip=0.0.0.0", f"--ServerApp.port={PORT}",
        f"--IdentityProvider.token={TOKEN}",
        "--ServerApp.allow_origin=*",
        "--ServerApp.allow_remote_access=True",
        "--ServerApp.disable_check_xsrf=True",
        "--no-browser", "--allow-root", f"--ServerApp.root_dir={ROOT}",
    ],
    stdout=open(f"{ROOT}/jupyter.log", "w"), stderr=subprocess.STDOUT,
)

for _ in range(30):
    try:
        req = urllib.request.Request(f"http://localhost:{PORT}/api",
                                     headers={"Authorization": f"token {TOKEN}"})
        if urllib.request.urlopen(req, timeout=2).status == 200:
            break
    except Exception:
        time.sleep(1)
if _JUPYTER.poll() is not None:
    raise RuntimeError(f"jupyter server exited — see {ROOT}/jupyter.log")

# Tunnel output goes to a file (not a pipe): an unread pipe fills up during a
# long session and stalls the tunnel.
TUNNEL_LOG = f"{ROOT}/cloudflared.log"
_TUNNEL = subprocess.Popen(
    [CF, "tunnel", "--url", f"http://localhost:{PORT}", "--no-autoupdate"],
    stdout=open(TUNNEL_LOG, "w"), stderr=subprocess.STDOUT,
)
URL = None
for _ in range(90):
    m = re.search(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", open(TUNNEL_LOG).read())
    if m:
        URL = m.group(0)
        break
    time.sleep(1)
if URL is None:
    raise RuntimeError(f"tunnel did not come up within 90s — see {TUNNEL_LOG}")

gpu = subprocess.run(
    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
    capture_output=True, text=True,
).stdout.strip() if shutil.which("nvidia-smi") else ""

print("\n" + "=" * 60)
print("thesis-mcp runtime is UP (Kaggle)" + (f"  ·  GPU: {gpu}" if gpu else "  ·  (no GPU — set Accelerator to GPU!)"))
print("=" * 60)
print("Run these locally (before starting Claude Code):\n")
print(f'  export JUPYTER_URL="{URL}"')
print(f'  export JUPYTER_TOKEN="{TOKEN}"')
print("\nThen in Claude Code:  connect_runtime  (it auto-detects /kaggle/working)")
print("Keep THIS cell running for the whole session.")
