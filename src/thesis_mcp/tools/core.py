"""Core tools: connect to the runtime, run code, and manage long training runs.

Design rule that shapes everything here: Colab/Kaggle VMs disconnect and MCP
calls are short request/response, so training is **fire-and-poll**. ``launch_training``
starts the job as a background process on the VM and returns immediately; you then
poll ``get_run_status`` / ``get_logs`` / ``get_metrics``. Metrics and checkpoints
are written to a per-run directory so a dropped connection never loses progress.
"""

import json
import os
import posixpath

from mcp.server.fastmcp import Image

from .. import config
from .. import runtime_state as rs

# Injected at the top of every launched training script. Gives the script a
# zero-dependency way to record metrics and checkpoints the tools can read back.
TRAIN_PREAMBLE = '''\
import os as _os, json as _json, time as _time
THESIS_RUN_DIR = _os.environ.get("THESIS_RUN_DIR", ".")

def log_metric(step=None, **kv):
    """Append one JSON-line metrics record for the MCP to read and plot."""
    rec = {"t": _time.time(), "step": step}
    rec.update(kv)
    with open(_os.path.join(THESIS_RUN_DIR, "metrics.jsonl"), "a") as _f:
        _f.write(_json.dumps(rec) + "\\n")

def save_checkpoint_file(src, name=None):
    """Copy a file into this run's checkpoints/ dir (persisted, survivable)."""
    import shutil
    d = _os.path.join(THESIS_RUN_DIR, "checkpoints")
    _os.makedirs(d, exist_ok=True)
    dst = _os.path.join(d, name or _os.path.basename(src))
    shutil.copy(src, dst)
    return dst

SEED = int(_os.environ.get("THESIS_SEED", "0"))
'''


def _img_from_bytes(data: bytes, ext: str = "png") -> Image:
    fmt = "jpeg" if ext.lower() in ("jpg", "jpeg") else ext.lower()
    return Image(data=data, format=fmt)


def launch_impl(script: str, run_name: str, requirements: str = "", env: dict = None):
    """Shared launcher used by launch_training and by rl_seed_sweep.

    Returns (ok: bool, run_dir: str, message: str).
    """
    run_dir = posixpath.join(rs.run_root(), run_name)
    rs.store.new_run(run_name, run_dir)
    full = TRAIN_PREAMBLE + "\n# ---- user script ----\n" + script

    rs.jupyter.execute(
        f"import os;os.makedirs(os.path.join({run_dir!r},'checkpoints'), exist_ok=True)",
        timeout=30,
    )
    rs.jupyter.upload_bytes(rs.to_rel(posixpath.join(run_dir, "train.py")), full.encode())

    setup = ""
    if requirements.strip():
        setup = f"subprocess.run('pip -q install {requirements.strip()}'.split(), check=False)\n"
    env_lines = ""
    for k, v in (env or {}).items():
        env_lines += f"env[{k!r}] = {str(v)!r}\n"

    launcher = (
        "import os, subprocess\n"
        f"RUN_DIR = {run_dir!r}\n"
        "os.makedirs(os.path.join(RUN_DIR,'checkpoints'), exist_ok=True)\n"
        f"{setup}"
        "env = dict(os.environ); env['THESIS_RUN_DIR'] = RUN_DIR\n"
        f"{env_lines}"
        "logf = open(os.path.join(RUN_DIR,'run.log'), 'w')\n"
        "p = subprocess.Popen(['python','-u','train.py'], cwd=RUN_DIR, "
        "stdout=logf, stderr=subprocess.STDOUT, env=env)\n"
        "open(os.path.join(RUN_DIR,'pid'),'w').write(str(p.pid))\n"
        "print('LAUNCHED_PID', p.pid)\n"
    )
    res = rs.jupyter.execute(launcher, timeout=120)
    if res.error:
        rs.store.update_run(run_name, status="failed_launch")
        return False, run_dir, res.error
    rs.store.update_run(run_name, status="running")
    return True, run_dir, res.text.strip()


def register(mcp):
    # -- connection ---------------------------------------------------------
    @mcp.tool()
    def connect_runtime(url: str = "", token: str = "") -> str:
        """Connect to (or re-attach to) the Colab/Kaggle Jupyter runtime.

        Pass the url/token printed by the bootstrap cell, or leave blank to use the
        JUPYTER_URL / JUPYTER_TOKEN environment variables. Safe to call every session —
        it re-attaches to an already-running kernel when one exists.
        """
        if url:
            rs.jupyter.configure(url, token)
        if not rs.jupyter.connected:
            return ("No runtime configured. Run the bootstrap cell in Colab/Kaggle, then "
                    "either call connect_runtime(url='https://...trycloudflare.com', token='...') "
                    "or set JUPYTER_URL / JUPYTER_TOKEN in the environment.")
        reused = rs.jupyter.kernel_alive()
        kid = rs.jupyter.ensure_kernel()
        detect = rs.jupyter.execute(
            "import os;print('/content' if os.path.isdir('/content') "
            "else ('/kaggle/working' if os.path.isdir('/kaggle/working') else os.getcwd()))",
            timeout=30,
        )
        croot = (detect.text.strip().splitlines() or ["/content"])[-1]
        rroot = posixpath.join(croot, "thesis_runs")
        rs.store.save_kernel(url=rs.jupyter.base_url, kernel_id=kid,
                             contents_root=croot, run_root=rroot)
        rs.jupyter.execute(f"import os;os.makedirs({rroot!r}, exist_ok=True)", timeout=30)
        gpu = rs.jupyter.execute(
            "import subprocess;print(subprocess.run("
            "['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader'],"
            "capture_output=True,text=True).stdout.strip() or 'no GPU visible')",
            timeout=30,
        )
        verb = "Re-attached to" if reused else "Started"
        return (f"{verb} kernel {kid}.\ncontents_root={croot}  run_root={rroot}\n"
                f"GPU: {gpu.text.strip()}")

    @mcp.tool()
    def runtime_status() -> str:
        """Report kernel liveness, Python/CUDA info, GPU, RAM and disk on the runtime."""
        if not rs.jupyter.connected:
            return "Not connected. Run connect_runtime first."
        code = (
            "import sys, subprocess, shutil, os\n"
            "print('python', sys.version.split()[0])\n"
            "try:\n"
            "    import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(),"
            " torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')\n"
            "except Exception as e:\n    print('torch not installed')\n"
            "print('cwd', os.getcwd())\n"
            "g = subprocess.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used,memory.total',"
            "'--format=csv,noheader'],capture_output=True,text=True).stdout.strip()\n"
            "print('gpu', g or 'none')\n"
            "du = shutil.disk_usage(os.getcwd()); print('disk_free_GB', round(du.free/1e9,1))\n"
        )
        return rs.jupyter.execute(code, timeout=40).text or "(no status)"

    # -- raw execution + files ---------------------------------------------
    @mcp.tool()
    def run_code(code: str, timeout: int = 120) -> list:
        """Execute Python on the runtime; returns stdout/results plus any PNG images.

        For quick, interactive work. Do NOT run long training here — it will hit the
        timeout. Use launch_training for anything that takes minutes.
        """
        res = rs.jupyter.execute(code, timeout=timeout)
        out: list = [res.text or "(no text output)"]
        out.extend(_img_from_bytes(b) for b in res.images)
        return out

    @mcp.tool()
    def upload_file(local_path: str, remote_path: str) -> str:
        """Upload a local file to the runtime (path is relative to the runtime's contents root)."""
        with open(local_path, "rb") as f:
            data = f.read()
        parent = posixpath.dirname(remote_path)
        if parent:
            abs_parent = posixpath.join(rs.contents_root(), parent)
            rs.jupyter.execute(f"import os;os.makedirs({abs_parent!r}, exist_ok=True)", timeout=30)
        rs.jupyter.upload_bytes(remote_path, data)
        return f"Uploaded {local_path} -> {remote_path} ({len(data)} bytes)"

    @mcp.tool()
    def download_file(remote_path: str, local_path: str) -> str:
        """Download a file from the runtime to the local machine."""
        data = rs.jupyter.download_bytes(remote_path)
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)
        return f"Downloaded {remote_path} -> {local_path} ({len(data)} bytes)"

    @mcp.tool()
    def fetch_image(remote_path: str) -> list:
        """Fetch an image file (png/jpg) from the runtime and show it inline.

        Use for prediction visualizations, Grad-CAM, rollout frames, or any figure
        your code saved to disk on the runtime.
        """
        data = rs.jupyter.download_bytes(remote_path)
        ext = remote_path.rsplit(".", 1)[-1] if "." in remote_path else "png"
        return [f"{remote_path}", _img_from_bytes(data, ext)]

    # -- fire-and-poll training --------------------------------------------
    @mcp.tool()
    def launch_training(script: str, run_name: str, requirements: str = "",
                        env_json: str = "") -> str:
        """Launch a training script as a background job on the runtime; returns immediately.

        The script may call the injected helpers ``log_metric(step, **kv)`` and
        ``save_checkpoint_file(path)``, and read ``SEED``. Poll with get_run_status /
        get_logs / get_metrics; plot with plot_metrics.

        requirements: space-separated pip packages to install first (e.g. "stable-baselines3 gymnasium").
        env_json: JSON object of extra environment variables for the run.
        """
        env = None
        if env_json.strip():
            try:
                env = json.loads(env_json)
            except json.JSONDecodeError:
                return f"env_json is not valid JSON: {env_json!r}"
        ok, run_dir, msg = launch_impl(script, run_name, requirements, env)
        if not ok:
            return f"Launch failed:\n{msg}"
        return (f"Launched '{run_name}' ({msg}). Dir: {run_dir}\n"
                f"Poll with get_run_status('{run_name}'), get_logs('{run_name}'), "
                f"plot_metrics('{run_name}', 'loss').")

    @mcp.tool()
    def get_run_status(run_name: str) -> str:
        """Check whether a launched run is still alive and how many metric rows it has logged."""
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'. Known: {[r['name'] for r in rs.store.list_runs()]}"
        rd = run["dir"]
        code = (
            f"import os\nrd = {rd!r}\npid = None\n"
            "try:\n    pid = int(open(os.path.join(rd,'pid')).read().strip())\nexcept Exception:\n    pass\n"
            "alive = False\n"
            "if pid is not None:\n"
            "    try:\n        os.kill(pid, 0); alive = True\n    except OSError:\n        alive = False\n"
            "mp = os.path.join(rd,'metrics.jsonl')\n"
            "rows = sum(1 for _ in open(mp)) if os.path.exists(mp) else 0\n"
            "last = list(open(mp))[-1].strip() if rows else ''\n"
            "print('PID', pid)\nprint('RUNNING', int(alive))\nprint('ROWS', rows)\nprint('LAST', last)\n"
        )
        res = rs.jupyter.execute(code, timeout=30)
        info = {}
        for line in res.text.splitlines():
            k, _, v = line.partition(" ")
            info[k] = v
        running = info.get("RUNNING") == "1"
        rs.store.update_run(run_name, status="running" if running else "stopped")
        return (f"run '{run_name}': {'RUNNING' if running else 'not running'} "
                f"(pid {info.get('PID')})\nmetric rows: {info.get('ROWS')}\n"
                f"last metric: {info.get('LAST') or '(none)'}")

    @mcp.tool()
    def get_logs(run_name: str, tail: int = 100) -> str:
        """Return the last ``tail`` lines of a run's stdout/stderr log."""
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        rd = run["dir"]
        code = (
            f"import os\np = os.path.join({rd!r}, 'run.log')\n"
            "if os.path.exists(p):\n"
            f"    print(chr(10).join(open(p, errors='replace').read().splitlines()[-{int(tail)}:]))\n"
            "else:\n    print('(no log yet)')\n"
        )
        return rs.jupyter.execute(code, timeout=30).text or "(empty)"

    @mcp.tool()
    def get_metrics(run_name: str, tail: int = 20) -> str:
        """Return the last ``tail`` logged metric records (JSON lines) for a run."""
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        rd = run["dir"]
        code = (
            f"import os\np = os.path.join({rd!r}, 'metrics.jsonl')\n"
            "if os.path.exists(p):\n"
            f"    print(''.join(open(p).readlines()[-{int(tail)}:]))\n"
            "else:\n    print('(no metrics yet)')\n"
        )
        return rs.jupyter.execute(code, timeout=30).text or "(none)"

    @mcp.tool()
    def stop_run(run_name: str) -> str:
        """Terminate a running training job."""
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        rd = run["dir"]
        code = (
            f"import os, signal\nrd = {rd!r}\n"
            "try:\n    pid = int(open(os.path.join(rd,'pid')).read().strip())\n"
            "    os.kill(pid, signal.SIGTERM); print('SENT SIGTERM to', pid)\n"
            "except Exception as e:\n    print('could not stop:', e)\n"
        )
        rs.store.update_run(run_name, status="stopped")
        return rs.jupyter.execute(code, timeout=30).text

    @mcp.tool()
    def list_runs() -> str:
        """List all training runs this MCP has launched (from the local registry)."""
        runs = rs.store.list_runs()
        if not runs:
            return "No runs yet."
        return "\n".join(f"- {r['name']}: {r.get('status','?')}  ({r['dir']})" for r in runs)

    @mcp.tool()
    def plot_metrics(run_name: str, keys: str) -> list:
        """Plot one or more metric series for a run and return the chart as an image.

        keys: comma-separated metric names, e.g. "loss,val_acc" or "reward".
        """
        run = rs.store.get_run(run_name)
        if not run:
            return [f"No run named '{run_name}'."]
        rd = run["dir"]
        key_list = [k.strip() for k in keys.split(",") if k.strip()]
        out_abs = posixpath.join(rd, "_plot.png")
        code = (
            "import json, os, matplotlib\nmatplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            f"rd = {rd!r}\nkeys = {key_list!r}\n"
            "rows = [json.loads(l) for l in open(os.path.join(rd,'metrics.jsonl'))] "
            "if os.path.exists(os.path.join(rd,'metrics.jsonl')) else []\n"
            "plt.figure(figsize=(7,4))\n"
            "for k in keys:\n"
            "    pts = [(r.get('step', i), r[k]) for i, r in enumerate(rows) if r.get(k) is not None]\n"
            "    if pts:\n        xs, ys = zip(*pts); plt.plot(xs, ys, label=k, marker='.')\n"
            "plt.legend(); plt.xlabel('step'); plt.title(" f"{run_name!r}" "); plt.grid(alpha=0.3)\n"
            f"plt.savefig({out_abs!r}, dpi=120, bbox_inches='tight'); print('rows', len(rows))\n"
        )
        res = rs.jupyter.execute(code, timeout=60)
        if res.error:
            return [f"Plot failed:\n{res.error}"]
        try:
            data = rs.jupyter.download_bytes(rs.to_rel(out_abs))
        except Exception as e:  # noqa: BLE001
            return [f"Rendered but could not fetch image: {e}\n{res.text}"]
        return [f"{run_name}: {keys} ({res.text.strip()})", _img_from_bytes(data)]

    # -- checkpoints (persist off the ephemeral VM) -------------------------
    @mcp.tool()
    def save_checkpoint(run_name: str, filename: str = "") -> str:
        """Download a run's checkpoint(s) to the local machine so they survive VM shutdown.

        filename: a single file in the run's checkpoints/ dir; if blank, the whole
        checkpoints/ dir is zipped on the runtime and downloaded.
        """
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        rd = run["dir"]
        local_dir = os.path.join(config.STATE_DIR, "checkpoints", run_name)
        os.makedirs(local_dir, exist_ok=True)
        if filename:
            remote = rs.to_rel(posixpath.join(rd, "checkpoints", filename))
            data = rs.jupyter.download_bytes(remote)
            local = os.path.join(local_dir, filename)
        else:
            bundle_abs = posixpath.join(rd, "checkpoints_bundle")
            rs.jupyter.execute(
                f"import shutil, os; shutil.make_archive({bundle_abs!r}, 'zip', "
                f"os.path.join({rd!r}, 'checkpoints'))",
                timeout=120,
            )
            data = rs.jupyter.download_bytes(rs.to_rel(bundle_abs + ".zip"))
            local = os.path.join(local_dir, "checkpoints.zip")
        with open(local, "wb") as f:
            f.write(data)
        return f"Saved checkpoint -> {local} ({len(data)} bytes)"

    @mcp.tool()
    def restore_checkpoint(run_name: str, local_filename: str) -> str:
        """Upload a locally-saved checkpoint file back into a run's checkpoints/ dir on the runtime."""
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        rd = run["dir"]
        local = os.path.join(config.STATE_DIR, "checkpoints", run_name, local_filename)
        with open(local, "rb") as f:
            data = f.read()
        remote = rs.to_rel(posixpath.join(rd, "checkpoints", local_filename))
        rs.jupyter.upload_bytes(remote, data)
        return f"Restored {local} -> {remote} ({len(data)} bytes)"
