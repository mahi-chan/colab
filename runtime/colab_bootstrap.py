# =====================================================================
# thesis-mcp  ·  COLAB BOOTSTRAP
# Paste this whole cell into a Google Colab notebook and RUN it.
#   1. First set the runtime to GPU:  Runtime > Change runtime type > GPU
#   2. Run this cell. Leave it running (it hosts the server + tunnel).
#   3. Copy the printed JUPYTER_URL / JUPYTER_TOKEN to your local machine.
# =====================================================================

# --- (optional) Kaggle credentials, needed for cv_load_dataset / kaggle_* ---
# import os
# os.environ["KAGGLE_USERNAME"] = "your_username"
# os.environ["KAGGLE_KEY"]      = "your_key"

import os, re, secrets, subprocess, time, urllib.request

TOKEN = secrets.token_hex(16)
PORT = 8888

# 1. Jupyter Server (full server = kernels + file/notebook API the MCP needs)
subprocess.run("pip -q install jupyter_server".split(), check=False)

# 2. cloudflared (free quick tunnel to expose the local port publicly)
CF = "/content/cloudflared"
if not os.path.exists(CF):
    urllib.request.urlretrieve(
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
        CF,
    )
    os.chmod(CF, 0o755)

# 3. Start the Jupyter server
_JUPYTER = subprocess.Popen(
    [
        "jupyter", "server",
        "--ServerApp.ip=0.0.0.0", f"--ServerApp.port={PORT}",
        f"--IdentityProvider.token={TOKEN}",
        "--ServerApp.allow_origin=*",
        "--ServerApp.allow_remote_access=True",
        "--ServerApp.disable_check_xsrf=True",
        "--no-browser", "--ServerApp.root_dir=/content",
    ],
    stdout=open("/content/jupyter.log", "w"), stderr=subprocess.STDOUT,
)

# wait until it answers
for _ in range(30):
    try:
        req = urllib.request.Request(f"http://localhost:{PORT}/api",
                                     headers={"Authorization": f"token {TOKEN}"})
        if urllib.request.urlopen(req, timeout=2).status == 200:
            break
    except Exception:
        time.sleep(1)

# 4. Start the tunnel and grab the public URL
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

gpu = subprocess.run(
    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
    capture_output=True, text=True,
).stdout.strip()

print("\n" + "=" * 60)
print("thesis-mcp runtime is UP" + (f"  ·  GPU: {gpu}" if gpu else "  ·  (no GPU — set Runtime type to GPU!)"))
print("=" * 60)
print("Run these locally (before starting Claude Code):\n")
print(f'  export JUPYTER_URL="{URL}"')
print(f'  export JUPYTER_TOKEN="{TOKEN}"')
print("\nThen in Claude Code:  connect_runtime")
print("\nKeep THIS cell running for the whole session.")
