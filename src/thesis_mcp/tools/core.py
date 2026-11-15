"""Core tools: connect to the runtime, run code, and manage long training runs.

Design rule that shapes everything here: remote machines disconnect and MCP
calls are short request/response, so training is **fire-and-poll**. ``launch_training``
starts the job as a background process on the VM and returns immediately; you then
poll ``get_run_status`` / ``get_logs`` / ``get_metrics``. Metrics and checkpoints
are written to a per-run directory so a dropped connection never loses progress.

A run lives either on the connected Jupyter runtime (Colab, Kaggle, or a Hugging Face
machine) or in its own Hugging Face batch job (``backend == "hf_job"``); the run tools
below work on both.
"""

import json
import os
import posixpath
import re
import shlex

from mcp.server.fastmcp import Image

from .. import config
from .. import runtime_state as rs
from ..connectors import hf
from . import _plots, hf_jobs

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
    """Copy a checkpoint file or folder into this run's checkpoints/ dir."""
    import shutil
    d = _os.path.join(THESIS_RUN_DIR, "checkpoints")
    _os.makedirs(d, exist_ok=True)
    dst = _os.path.join(d, name or _os.path.basename(_os.path.normpath(src)))
    if _os.path.abspath(src) == _os.path.abspath(dst):
        return dst
    if _os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy(src, dst)
    return dst

SEED = int(_os.environ.get("THESIS_SEED", "0"))
'''


def _img_from_bytes(data: bytes, ext: str = "png") -> Image:
    fmt = "jpeg" if ext.lower() in ("jpg", "jpeg") else ext.lower()
    return Image(data=data, format=fmt)


def check_run_name(run_name: str) -> str:
    """Return a problem description, or "" when the name is usable.

    A run name becomes a directory on the runtime and a Hub repo name, so keep it simple.
    """
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", run_name) and not run_name.endswith("."):
        return ""
    return (f"Invalid run_name {run_name!r}: use letters, digits, '-', '_' and '.', "
            "starting with a letter or digit (max 80 characters).")


def is_job(run: dict) -> bool:
    return run.get("backend") == "hf_job"


def connect_impl(**remember) -> str:
    """Attach to a kernel on the configured Jupyter server and remember the connection.

    ``remember`` is saved with it (e.g. how to authenticate again in a later session).
    """
    reused = rs.jupyter.kernel_alive()
    kid = rs.jupyter.ensure_kernel()
    detect = rs.jupyter.execute(
        "import os;print('/content' if os.path.isdir('/content') "
        "else ('/kaggle/working' if os.path.isdir('/kaggle/working') else os.getcwd()))",
        timeout=30,
    )
    croot = config.CONTENTS_ROOT or (detect.text.strip().splitlines() or ["/content"])[-1]
    rroot = config.RUN_ROOT or posixpath.join(croot, "thesis_runs")
    rs.store.set_kernel(url=rs.jupyter.base_url, kernel_id=kid,
                        contents_root=croot, run_root=rroot, **remember)
    rs.jupyter.execute(f"import os;os.makedirs({rroot!r}, exist_ok=True)", timeout=30)
    gpu = rs.jupyter.execute(
        "import subprocess, shutil\n"
        "print((subprocess.run(['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader'],"
        "capture_output=True,text=True).stdout.strip() if shutil.which('nvidia-smi') else '') "
        "or 'no GPU visible')",
        timeout=30,
    )
    verb = "Re-attached to" if reused else "Started"
    return (f"{verb} kernel {kid}.\ncontents_root={croot}  run_root={rroot}\n"
            f"GPU: {gpu.text.strip()}")


# Remote snippet: defines _pid_alive(pid). The training process is a child of the
# kernel, so once it exits it lingers as a zombie that os.kill(pid, 0) still reports
# as alive; reap it (or check /proc state) so finished runs read as finished.
PID_ALIVE_SNIPPET = '''\
import os as _os
def _pid_alive(pid):
    try:
        if _os.waitpid(pid, _os.WNOHANG)[0] == pid:
            return False
    except ChildProcessError:
        pass
    except OSError:
        pass
    try:
        _os.kill(pid, 0)
    except OSError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as _f:
            return _f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True
'''


def launch_impl(script: str, run_name: str, requirements: str = "", env: dict = None):
    """Shared launcher used by launch_training and by rl_seed_sweep.

    Returns (ok: bool, run_dir: str, message: str).
    """
    problem = check_run_name(run_name)
    if problem:
        return False, "", problem
    existing = rs.store.get_run(run_name)
    if existing and is_job(existing) and hf_jobs.job_is_active(existing):
        return False, "", (f"run '{run_name}' is still running as a Hugging Face job; "
                           "stop_run it first or pick another run_name.")
    run_dir = posixpath.join(rs.run_root(), run_name)
    full = TRAIN_PREAMBLE + "\n# ---- user script ----\n" + script

    # Refuse to clobber a run that is still alive under the same name, and clear the
    # previous attempt's metrics/log so curves don't mix two runs (checkpoints are kept).
    prep = rs.jupyter.execute(
        PID_ALIVE_SNIPPET
        + f"import os\nrd = {run_dir!r}\n"
        "os.makedirs(os.path.join(rd,'checkpoints'), exist_ok=True)\n"
        "pid = None\n"
        "try:\n    pid = int(open(os.path.join(rd,'pid')).read().strip())\nexcept Exception:\n    pass\n"
        "if pid is not None and _pid_alive(pid):\n    print('BUSY', pid)\n"
        "else:\n"
        "    for f in ('metrics.jsonl', 'run.log', 'pid'):\n"
        "        try:\n            os.remove(os.path.join(rd, f))\n"
        "        except FileNotFoundError:\n            pass\n"
        "    print('READY')\n",
        timeout=30,
    )
    if prep.error:
        return False, run_dir, prep.error
    if "BUSY" in prep.text:
        return False, run_dir, (f"run '{run_name}' is still running ({prep.text.strip()}); "
                                "stop_run it first or pick another run_name.")

    rs.store.new_run(run_name, run_dir)
    rs.jupyter.upload_bytes(rs.to_rel(posixpath.join(run_dir, "train.py")), full.encode())

    # pip install runs inside the background job (not in the kernel), so a slow
    # install can't hit the tool timeout; its output lands in run.log.
    cmd = "exec python -u train.py"
    if requirements.strip():
        pkgs = " ".join(shlex.quote(p) for p in shlex.split(requirements))
        cmd = f"pip -q install {pkgs}; " + cmd
    env_lines = ""
    for k, v in (env or {}).items():
        env_lines += f"env[{k!r}] = {str(v)!r}\n"

    launcher = (
        "import os, subprocess\n"
        f"RUN_DIR = {run_dir!r}\n"
        "os.makedirs(os.path.join(RUN_DIR,'checkpoints'), exist_ok=True)\n"
        "env = dict(os.environ); env['THESIS_RUN_DIR'] = RUN_DIR\n"
        f"{env_lines}"
        "logf = open(os.path.join(RUN_DIR,'run.log'), 'w')\n"
        # start_new_session: a kernel interrupt/restart (signals the kernel's process
        # group) must not kill the background training job.
        f"p = subprocess.Popen(['bash','-c',{cmd!r}], cwd=RUN_DIR, "
        "stdout=logf, stderr=subprocess.STDOUT, env=env, start_new_session=True)\n"
        "open(os.path.join(RUN_DIR,'pid'),'w').write(str(p.pid))\n"
        "print('LAUNCHED_PID', p.pid)\n"
    )
    res = rs.jupyter.execute(launcher, timeout=60)
    if res.error:
        rs.store.update_run(run_name, status="failed_launch")
        return False, run_dir, res.error
    rs.store.update_run(run_name, status="running")
    return True, run_dir, res.text.strip()


def register(mcp):
    # -- connection ---------------------------------------------------------
    @mcp.tool()
    @hf_jobs.hf_errors
    def connect_runtime(url: str = "", token: str = "", hf_auth: bool = False) -> str:
        """Connect to (or re-attach to) a Jupyter runtime: Colab, Kaggle, or a Hugging Face Space.

        Pass the url/token printed by the bootstrap cell, or leave blank to use the
        JUPYTER_URL / JUPYTER_TOKEN environment variables. Safe to call every session —
        it re-attaches to an already-running kernel when one exists.
        (For a machine rented with hf_runtime_start, call hf_runtime_connect instead.)

        hf_auth: set True for a JupyterLab running in a Hugging Face Space
                 (url "https://<user>-<space>.hf.space", token = the Space's JUPYTER_TOKEN);
                 your Hugging Face token is then sent too, as private Spaces require.
        """
        remember = {}
        if url:
            bearer = hf.token() if hf_auth else ""
            rs.jupyter.configure(url, token or config.JUPYTER_TOKEN, bearer=bearer)
            if hf_auth:
                remember["auth"] = "hf"
        elif rs.jupyter.bearer:
            remember = {k: v for k, v in rs.store.get_kernel().items()
                        if k in ("auth", "nonce", "job_id")}
        if not rs.jupyter.connected:
            return ("No runtime configured. Colab/Kaggle: run the bootstrap cell, then either "
                    "call connect_runtime(url='https://...trycloudflare.com', token='...') "
                    "or set JUPYTER_URL / JUPYTER_TOKEN in the environment. "
                    "Hugging Face: call hf_runtime_start, then hf_runtime_connect.")
        return connect_impl(**remember)

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
            "'--format=csv,noheader'],capture_output=True,text=True).stdout.strip() "
            "if shutil.which('nvidia-smi') else ''\n"
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
    @hf_jobs.hf_errors
    def get_run_status(run_name: str) -> str:
        """Check whether a launched run is still alive and how many metric rows it has logged."""
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'. Known: {[r['name'] for r in rs.store.list_runs()]}"
        if is_job(run):
            return hf_jobs.job_status_text(run)
        rd = run["dir"]
        code = (
            PID_ALIVE_SNIPPET
            + f"import os\nrd = {rd!r}\npid = None\n"
            "try:\n    pid = int(open(os.path.join(rd,'pid')).read().strip())\nexcept Exception:\n    pass\n"
            "alive = pid is not None and _pid_alive(pid)\n"
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
    @hf_jobs.hf_errors
    def get_logs(run_name: str, tail: int = 100) -> str:
        """Return the last ``tail`` lines of a run's stdout/stderr log."""
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        if is_job(run):
            return hf_jobs.job_logs_text(run, int(tail))
        rd = run["dir"]
        code = (
            f"import os\np = os.path.join({rd!r}, 'run.log')\n"
            "if os.path.exists(p):\n"
            f"    print(chr(10).join(open(p, errors='replace').read().splitlines()[-{int(tail)}:]))\n"
            "else:\n    print('(no log yet)')\n"
        )
        return rs.jupyter.execute(code, timeout=30).text or "(empty)"

    @mcp.tool()
    @hf_jobs.hf_errors
    def get_metrics(run_name: str, tail: int = 20) -> str:
        """Return the last ``tail`` logged metric records (JSON lines) for a run."""
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        if is_job(run):
            rows = hf_jobs.job_metric_rows(run)[-int(tail):]
            return "\n".join(json.dumps(r) for r in rows) or "(no metrics yet)"
        rd = run["dir"]
        code = (
            f"import os\np = os.path.join({rd!r}, 'metrics.jsonl')\n"
            "if os.path.exists(p):\n"
            f"    print(''.join(open(p).readlines()[-{int(tail)}:]))\n"
            "else:\n    print('(no metrics yet)')\n"
        )
        return rs.jupyter.execute(code, timeout=30).text or "(none)"

    @mcp.tool()
    @hf_jobs.hf_errors
    def stop_run(run_name: str) -> str:
        """Terminate a running training job (for a Hugging Face job this stops its billing)."""
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        if is_job(run):
            return hf_jobs.job_stop(run)
        rd = run["dir"]
        code = (
            f"import os, signal\nrd = {rd!r}\n"
            "try:\n    pid = int(open(os.path.join(rd,'pid')).read().strip())\n"
            "    try:\n        os.killpg(pid, signal.SIGTERM)\n    except OSError:\n        os.kill(pid, signal.SIGTERM)\n    print('SENT SIGTERM to', pid)\n"
            "except Exception as e:\n    print('could not stop:', e)\n"
        )
        rs.store.update_run(run_name, status="stopped")
        return rs.jupyter.execute(code, timeout=30).text

    @mcp.tool()
    def list_runs() -> str:
        """List all training runs this MCP has launched (from the local registry).

        The status shown is the last one seen; get_run_status checks a run live.
        """
        runs = rs.store.list_runs()
        if not runs:
            return "No runs yet."
        return "\n".join(
            f"- {r['name']}: {r.get('status', '?')}  "
            + (f"(Hugging Face job {r['job_id']} on {r.get('flavor')})" if is_job(r) else f"({r['dir']})")
            for r in runs)

    @mcp.tool()
    @hf_jobs.hf_errors
    def plot_metrics(run_name: str, keys: str) -> list:
        """Plot one or more metric series for a run and return the chart as an image.

        keys: comma-separated metric names, e.g. "loss,val_acc" or "reward".
        """
        run = rs.store.get_run(run_name)
        if not run:
            return [f"No run named '{run_name}'."]
        key_list = [k.strip() for k in keys.split(",") if k.strip()]
        if is_job(run):
            rows = hf_jobs.job_metric_rows(run)
            return [f"{run_name}: {keys} (rows {len(rows)})",
                    _img_from_bytes(_plots.plot_png(rows, key_list, run_name))]
        rd = run["dir"]
        out_abs = posixpath.join(rd, "_plot.png")
        code = (
            "import json, os, matplotlib\nmatplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            f"rd = {rd!r}\nkeys = {key_list!r}\n"
            "rows = [json.loads(l) for l in open(os.path.join(rd,'metrics.jsonl'))] "
            "if os.path.exists(os.path.join(rd,'metrics.jsonl')) else []\n"
            "plt.figure(figsize=(7,4))\n"
            "for k in keys:\n"
            "    pts = [((r['step'] if r.get('step') is not None else i), r[k]) for i, r in enumerate(rows) if r.get(k) is not None]\n"
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
    @hf_jobs.hf_errors
    def save_checkpoint(run_name: str, filename: str = "") -> str:
        """Download a run's checkpoint(s) to the local machine so they survive VM shutdown.

        filename: a single file in the run's checkpoints/ dir; if blank, the whole
        checkpoints/ dir is zipped on the runtime and downloaded. For a Hugging Face
        job the checkpoints come from the run's Hub repo instead.
        """
        run = rs.store.get_run(run_name)
        if not run:
            return f"No run named '{run_name}'."
        local_dir = os.path.join(config.STATE_DIR, "checkpoints", run_name)
        os.makedirs(local_dir, exist_ok=True)
        if is_job(run):
            if filename:
                path = hf.api().hf_hub_download(run["hub_repo"], filename, local_dir=local_dir,
                                                token=hf.token())
            else:
                path = hf.api().snapshot_download(run["hub_repo"], local_dir=local_dir,
                                                  token=hf.token())
            return f"Downloaded {run['hub_repo']} -> {path}"
        rd = run["dir"]
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
        if is_job(run):
            return (f"'{run_name}' ran as a Hugging Face job; its checkpoints already live in "
                    f"the Hub repo {run['hub_repo']} — load them from there in the next job.")
        rd = run["dir"]
        local = os.path.join(config.STATE_DIR, "checkpoints", run_name, local_filename)
        with open(local, "rb") as f:
            data = f.read()
        remote = rs.to_rel(posixpath.join(rd, "checkpoints", local_filename))
        rs.jupyter.upload_bytes(remote, data)
        return f"Restored {local} -> {remote} ({len(data)} bytes)"
