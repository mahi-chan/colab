# =====================================================================
# thesis-mcp  ·  KAGGLE BOOTSTRAP
# Paste into a Kaggle Notebook and RUN it.
#   1. Notebook settings: Accelerator = GPU, and Internet = ON.
#   2. Run this cell and leave it running.
#   3. Copy the printed JUPYTER_URL / JUPYTER_TOKEN to your local machine.
# Kaggle credentials are already configured inside Kaggle notebooks, so
# cv_load_dataset / kaggle_* work out of the box here.
# =====================================================================

import os, re, secrets, subprocess, time, urllib.request

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
        "--no-browser", f"--ServerApp.root_dir={ROOT}",
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

_TUNNEL = subprocess.Popen(
    [CF, "tunnel", "--url", f"http://localhost:{PORT}", "--no-autoupdate"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
)
URL = None
_t0 = time.time()
for line in _TUNNEL.stdout:
    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
    if m:
        URL = m.group(0)
        break
    if time.time() - _t0 > 90:
        break

print("\n" + "=" * 60)
print("thesis-mcp runtime is UP (Kaggle)")
print("=" * 60)
print("Run these locally (before starting Claude Code):\n")
print(f'  export JUPYTER_URL="{URL}"')
print(f'  export JUPYTER_TOKEN="{TOKEN}"')
print("\nAlso set  THESIS_CONTENTS_ROOT=/kaggle/working  locally, then call connect_runtime.")
print("Keep THIS cell running for the whole session.")
