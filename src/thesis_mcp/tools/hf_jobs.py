"""Hugging Face Jobs: rented, pay-per-minute machines (CPU or GPU).

Two ways to use them:

* **Batch** — ``hf_job_launch`` runs one training script on its own machine, which
  shuts down (and stops billing) the moment the script ends. Best for long trainings
  such as LLM fine-tuning. The run is tracked like any other, so ``get_run_status``,
  ``get_logs``, ``get_metrics``, ``plot_metrics`` and ``stop_run`` all work on it.
* **Interactive** — ``hf_runtime_start`` rents a machine running Jupyter, and
  ``hf_runtime_connect`` attaches to it. After that every runtime tool (``run_code``,
  ``launch_training``, notebooks, RL/CV/Kaggle tools) runs on that machine, exactly as
  on Colab or Kaggle.

Every job gets an explicit time limit: Hugging Face bills until a job ends.
"""

import base64
import datetime
import functools
import json
import secrets
import shlex
import time
from pathlib import Path

from huggingface_hub.errors import HfHubHTTPError

from .. import config
from .. import runtime_state as rs
from ..connectors import hf

METRIC_MARKER = "@@THESIS_METRIC@@"
RUNTIME_PORT = 8888
RUNTIME_ROOT = "/workspace"
ACTIVE_STAGES = ("RUNNING", "SCHEDULING")

# Injected at the top of every batch-job script. Same helper names as on a Jupyter
# runtime, so one training script runs unchanged on Colab, Kaggle or a Hugging Face job.
# A job's disk disappears when it ends, so metrics go to the log (which Hugging Face
# keeps) and checkpoints go straight to a private Hub repo.
JOB_PREAMBLE = '''\
import os as _os, json as _json, time as _time
THESIS_RUN_DIR = _os.environ.get("THESIS_RUN_DIR") or "/tmp/thesis_run"
_os.makedirs(_os.path.join(THESIS_RUN_DIR, "checkpoints"), exist_ok=True)
THESIS_HUB_REPO = _os.environ.get("THESIS_HUB_REPO", "")

def log_metric(step=None, **kv):
    """Record one metrics row (read back by get_metrics / plot_metrics)."""
    rec = {"t": _time.time(), "step": step}
    rec.update(kv)
    print("@@THESIS_METRIC@@" + _json.dumps(rec), flush=True)

def save_checkpoint_file(src, name=None):
    """Upload a checkpoint file or folder to this run's private Hub repo."""
    from huggingface_hub import HfApi
    hub = HfApi()
    hub.create_repo(THESIS_HUB_REPO, private=True, exist_ok=True)
    dest = name or _os.path.basename(_os.path.normpath(src))
    if _os.path.isdir(src):
        hub.upload_folder(folder_path=src, repo_id=THESIS_HUB_REPO, path_in_repo=dest)
    else:
        hub.upload_file(path_or_fileobj=src, path_in_repo=dest, repo_id=THESIS_HUB_REPO)
    return THESIS_HUB_REPO + "/" + dest

SEED = int(_os.environ.get("THESIS_SEED", "0"))
'''


def hf_errors(fn):
    """Turn Hugging Face failures into errors that say what to do about them."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except hf.HfNotLoggedIn as exc:
            raise RuntimeError(str(exc)) from None
        except HfHubHTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            hint = {
                401: "The Hugging Face token is missing or invalid.",
                402: "Payment required: add credits at https://huggingface.co/settings/billing.",
                403: "The token lacks permission for this. Use a token with write access.",
                404: "Not found: check the name, and that the token can see it.",
            }.get(status, "")
            raise RuntimeError(f"Hugging Face API error ({status}): {exc} {hint}".strip()) from None

    return wrapper


def _stage(job) -> str:
    stage = job.status.stage
    return str(getattr(stage, "value", stage))


def _age(job) -> str:
    start = job.started_at or job.created_at
    if not start:
        return "?"
    end = job.finished_at or datetime.datetime.now(datetime.timezone.utc)
    minutes = (end - start).total_seconds() / 60
    return f"{minutes:.0f} min" if minutes < 120 else f"{minutes / 60:.1f} h"


def _flavor(job) -> str:
    return str(getattr(job.flavor, "value", job.flavor) or "cpu-basic")


# -- batch runs: used by the run tools in core.py -----------------------------
def job_is_active(run: dict) -> bool:
    try:
        return _stage(hf.api().inspect_job(job_id=run["job_id"])) in ACTIVE_STAGES
    except HfHubHTTPError:
        return False  # the job no longer exists


def job_log_lines(run: dict, tail: int = 0) -> list:
    lines = hf.api().fetch_job_logs(job_id=run["job_id"], tail=tail or None)
    return [str(line).rstrip("\n") for line in lines]


def job_metric_rows(run: dict) -> list:
    rows = []
    for line in job_log_lines(run):
        _, marker, payload = line.partition(METRIC_MARKER)
        if marker:
            try:
                rows.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return rows


def job_status_text(run: dict) -> str:
    job = hf.api().inspect_job(job_id=run["job_id"])
    stage = _stage(job)
    rs.store.update_run(run["name"], status=stage.lower())
    rows = job_metric_rows(run)
    text = (f"run '{run['name']}': {stage} on {_flavor(job)} ({_age(job)})\n"
            f"metric rows: {len(rows)}\n"
            f"last metric: {json.dumps(rows[-1]) if rows else '(none)'}\n"
            f"checkpoints: https://huggingface.co/{run.get('hub_repo')}\njob page: {job.url}")
    if job.status.message:
        text += f"\nmessage: {job.status.message}"
    return text


def job_logs_text(run: dict, tail: int) -> str:
    lines = [ln for ln in job_log_lines(run) if METRIC_MARKER not in ln]
    return "\n".join(lines[-tail:]) or "(no log yet)"


def job_stop(run: dict) -> str:
    hf.api().cancel_job(job_id=run["job_id"])
    rs.store.update_run(run["name"], status="canceled")
    return f"Canceled Hugging Face job {run['job_id']} (run '{run['name']}'). Billing has stopped."


def launch_job_impl(script: str, run_name: str, flavor: str, timeout: str,
                    requirements: str = "", env: dict = None, image: str = ""):
    """Start a batch job. Returns (ok, message)."""
    token = hf.token()
    existing = rs.store.get_run(run_name)
    if existing and existing.get("backend") == "hf_job" and job_is_active(existing):
        return False, (f"run '{run_name}' is still running as job {existing['job_id']}; "
                       "stop_run it first or pick another run_name.")

    hub_repo = f"{hf.username()}/{run_name}"
    script_dir = Path(config.STATE_DIR) / "jobs" / run_name
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / "train.py"
    script_path.write_text(JOB_PREAMBLE + "\n# ---- user script ----\n" + script)

    job_env = {"THESIS_HUB_REPO": hub_repo}
    job_env.update({str(k): str(v) for k, v in (env or {}).items()})
    job = hf.api().run_uv_job(
        str(script_path),
        dependencies=["huggingface_hub", *shlex.split(requirements)],
        image=image or None,
        env=job_env,
        secrets={"HF_TOKEN": token},
        flavor=flavor,
        timeout=timeout,
        name=run_name,
        labels={"thesis-mcp": "run"},
    )
    rs.store.new_run(run_name, "", meta={
        "backend": "hf_job", "job_id": job.id, "url": job.url, "flavor": flavor,
        "hub_repo": hub_repo, "status": "running",
    })
    return True, (f"Launched '{run_name}' as Hugging Face job {job.id} on {flavor} "
                  f"(time limit {timeout}).\nJob page: {job.url}\n"
                  f"Checkpoints saved with save_checkpoint_file go to https://huggingface.co/{hub_repo}\n"
                  f"Poll with get_run_status('{run_name}') / get_logs('{run_name}'); "
                  f"cancel with stop_run('{run_name}').")


def register(mcp, connect_impl):
    @mcp.tool()
    @hf_errors
    def hf_hardware() -> str:
        """List the machines Hugging Face rents for jobs, with specs and price per hour."""
        lines = ["flavor | cpu | ram | gpu | $/hour"]
        for hw in hf.api().list_jobs_hardware(token=hf.token()):
            acc = hw.accelerator
            gpu = f"{acc.quantity}x {acc.model} ({acc.vram})" if acc else "-"
            per_hour = hw.unit_cost_usd * (60 if hw.unit_label == "minute" else 1)
            lines.append(f"{hw.name} | {hw.cpu} | {hw.ram} | {gpu} | {per_hour:.2f}")
        return "\n".join(lines)

    @mcp.tool()
    @hf_errors
    def hf_job_launch(script: str, run_name: str, flavor: str = "cpu-basic",
                      timeout: str = "1h", requirements: str = "", env_json: str = "",
                      image: str = "") -> str:
        """Run a training script on its own rented Hugging Face machine; returns immediately.

        The machine is billed per minute and stops when the script ends, fails, or hits
        ``timeout`` — so set ``timeout`` generously for real trainings (e.g. "6h").
        The script may use the injected helpers ``log_metric(step, **kv)``,
        ``save_checkpoint_file(path)`` (uploads a file or folder to the private Hub repo
        ``<you>/<run_name>``) and ``SEED``. Follow it with get_run_status / get_logs /
        get_metrics / plot_metrics, cancel with stop_run, fetch results with save_checkpoint.

        flavor: machine type from hf_hardware, e.g. "t4-small", "a10g-small", "a100-large".
        timeout: time limit such as "30m", "2h", "1d".
        requirements: space-separated pip packages, e.g. "torch transformers peft datasets".
        env_json: JSON object of extra environment variables.
        image: optional Docker image that has `uv` installed (default: a plain Python image;
               pip-installed torch brings its own CUDA libraries).
        """
        from .core import check_run_name

        problem = check_run_name(run_name)
        if problem:
            return problem
        env = None
        if env_json.strip():
            try:
                env = json.loads(env_json)
            except json.JSONDecodeError:
                return f"env_json is not valid JSON: {env_json!r}"
        ok, message = launch_job_impl(script, run_name, flavor, timeout, requirements, env, image)
        return message if ok else f"Launch failed: {message}"

    @mcp.tool()
    @hf_errors
    def hf_job_list(include_finished: bool = False) -> str:
        """List your Hugging Face jobs. By default only those running (and billing) right now."""
        status = None if include_finished else list(ACTIVE_STAGES)
        lines = []
        for i, job in enumerate(hf.api().list_jobs(status=status, token=hf.token())):
            if i >= 30:
                lines.append("... (more not shown)")
                break
            name = (job.labels or {}).get("name", "")
            lines.append(f"- {job.id}  {_stage(job)}  {_flavor(job)}  {_age(job)}  {name}")
        if not lines:
            return "No jobs." if include_finished else "No jobs are running; nothing is billing."
        return "\n".join(lines)

    @mcp.tool()
    @hf_errors
    def hf_job_cancel(job_id: str) -> str:
        """Cancel any Hugging Face job by id (from hf_job_list), stopping its billing."""
        hf.api().cancel_job(job_id=job_id, token=hf.token())
        return f"Canceled job {job_id}."

    # -- interactive runtime ------------------------------------------------
    @mcp.tool()
    @hf_errors
    def hf_runtime_start(flavor: str = "cpu-basic", timeout: str = "2h",
                         idle_minutes: int = 30, image: str = "") -> str:
        """Rent a Hugging Face machine running Jupyter, to use like a Colab/Kaggle runtime.

        Returns at once; then call hf_runtime_connect (the machine needs a minute or two).
        Billing runs per minute until hf_runtime_stop, the ``timeout``, or ``idle_minutes``
        with nothing running — whichever comes first. The disk is temporary: push results
        with hf_push_run or save_checkpoint before stopping.

        flavor: machine type from hf_hardware, e.g. "t4-small", "a10g-small", "l4x1".
        timeout: hard time limit such as "2h" or "8h".
        idle_minutes: shut down after this long with no activity and no run in progress
                      (0 disables the idle shutdown).
        image: Docker image with Python 3; defaults to an official PyTorch + CUDA image.
        """
        token = hf.token()
        current = rs.store.get_section("hf_runtime")
        if current.get("job_id"):
            try:
                if _stage(hf.api().inspect_job(job_id=current["job_id"])) in ACTIVE_STAGES:
                    return (f"A Hugging Face runtime is already running (job {current['job_id']}, "
                            f"{current.get('flavor')}). Call hf_runtime_connect to use it, or "
                            "hf_runtime_stop first.")
            except HfHubHTTPError:
                pass  # the remembered job is gone; start a new one

        nonce = secrets.token_hex(8)
        entrypoint = (Path(__file__).parent.parent / "remote" / "hf_entrypoint.py").read_bytes()
        boot = ("import base64,sys;"
                "exec(compile(base64.b64decode(sys.argv[1]),'hf_entrypoint.py','exec'))")
        image = image or config.HF_RUNTIME_IMAGE
        job = hf.api().run_job(
            image=image,
            command=["python3", "-c", boot, base64.b64encode(entrypoint).decode()],
            env={
                "THESIS_PORT": str(RUNTIME_PORT),
                "THESIS_ROOT": RUNTIME_ROOT,
                "THESIS_IDLE_MINUTES": str(int(idle_minutes)),
                "THESIS_ARCHIVE_REPO": f"{hf.username()}/thesis-mcp-archive",
            },
            secrets={"JUPYTER_TOKEN": hf.jupyter_token(nonce), "HF_TOKEN": token},
            flavor=flavor,
            timeout=timeout,
            expose=[RUNTIME_PORT],
            name="thesis-mcp-runtime",
            labels={"thesis-mcp": "runtime"},
        )
        rs.store.set_section("hf_runtime", {
            "job_id": job.id, "nonce": nonce, "flavor": flavor, "url": job.url, "image": image,
        })
        idle = f"{idle_minutes} idle minutes" if idle_minutes > 0 else "no idle shutdown"
        return (f"Started Hugging Face runtime: job {job.id} on {flavor} "
                f"(time limit {timeout}, {idle}).\nJob page: {job.url}\n"
                "Billing has started. Call hf_runtime_connect in about a minute; "
                "call hf_runtime_stop when done.")

    @mcp.tool()
    @hf_errors
    def hf_runtime_connect(wait_seconds: int = 90) -> str:
        """Attach to the Hugging Face runtime started with hf_runtime_start.

        Safe to call repeatedly and in every new session: it reports progress while the
        machine is still starting, and re-attaches to the same kernel once it is up.
        """
        rt = rs.store.get_section("hf_runtime")
        if not rt.get("job_id"):
            return "No Hugging Face runtime has been started. Call hf_runtime_start first."
        token = hf.token()
        deadline = time.time() + max(0, wait_seconds)
        while True:
            job = hf.api().inspect_job(job_id=rt["job_id"])
            stage = _stage(job)
            if stage not in ACTIVE_STAGES:
                rs.store.set_section("hf_runtime", {})
                detail = f" ({job.status.message})" if job.status.message else ""
                return (f"The runtime job {rt['job_id']} has ended: {stage}{detail}. "
                        "Start a new one with hf_runtime_start.")
            urls = job.status.expose_urls or []
            if stage == "RUNNING" and urls:
                url = next((u for u in urls if f"--{RUNTIME_PORT}." in u), urls[0])
                rs.jupyter.configure(url, hf.jupyter_token(rt["nonce"]), bearer=token)
                if rs.jupyter.ping():
                    return connect_impl(auth="hf", nonce=rt["nonce"], job_id=rt["job_id"])
            if time.time() >= deadline:
                what = ("the machine is up and Jupyter is still starting" if stage == "RUNNING"
                        else "Hugging Face is still allocating the machine")
                return (f"Not ready yet: {what} (job {rt['job_id']}, {_age(job)}). "
                        "Call hf_runtime_connect again in 30 seconds; get details from "
                        f"the job page {job.url}")
            time.sleep(5)

    @mcp.tool()
    @hf_errors
    def hf_runtime_stop() -> str:
        """Shut down the Hugging Face runtime and stop its billing.

        Everything on its disk is lost: push results first (hf_push_run / save_checkpoint).
        """
        rt = rs.store.get_section("hf_runtime")
        if not rt.get("job_id"):
            return "No Hugging Face runtime is recorded. Check hf_job_list for anything still running."
        hf.api().cancel_job(job_id=rt["job_id"], token=hf.token())
        rs.store.set_section("hf_runtime", {})
        if rs.store.get_kernel().get("job_id") == rt["job_id"]:
            rs.store.set_kernel()
            rs.jupyter.disconnect()
        return f"Stopped the Hugging Face runtime (job {rt['job_id']}). Billing has stopped."
