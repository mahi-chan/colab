"""Hugging Face tools.

The Hub client is a spec-checked mock (see conftest), so every call these tools make is
validated against the installed ``huggingface_hub`` signatures; responses are built with
the library's own classes from API-shaped data. The code that runs *on* the rented
machine (job preamble, runtime entrypoint) is executed for real, locally.
"""

import json
import os
import subprocess
import sys
import time

import pytest
import requests
from conftest import call, free_port, remote_env, wait_for_jupyter
from huggingface_hub import SpaceRuntime
from huggingface_hub._jobs_api import JobHardwareInfo, JobInfo
from huggingface_hub.errors import HfHubHTTPError

from thesis_mcp import config
from thesis_mcp import runtime_state as rs
from thesis_mcp.connectors import hf
from thesis_mcp.tools import hf_jobs

OWNER = {"id": "u1", "name": "alice", "type": "user"}


def job(job_id="job123", stage="RUNNING", **extra):
    data = {"id": job_id, "owner": OWNER, "flavor": "t4-small",
            "createdAt": "2026-11-14T10:00:00.000Z", "startedAt": "2026-11-14T10:01:00.000Z",
            "status": {"stage": stage}, "labels": {"name": "demo"}}
    data.update(extra)
    return JobInfo(**data)


SCRIPT = '''
for i in range(3):
    log_metric(step=i, loss=1.0 / (i + 1), reward=float(i))
open("model.pt", "w").write("weights")
print("saved to", save_checkpoint_file("model.pt"))
print("seed", SEED)
'''


# -- batch jobs ---------------------------------------------------------------
def test_job_launch_and_follow(hub, tmp_path):
    hub.run_uv_job.return_value = job()
    text, _ = call("hf_job_launch", script=SCRIPT, run_name="llm1", flavor="t4-small",
                   timeout="3h", requirements="torch transformers", env_json='{"THESIS_SEED": "5"}')
    assert "Launched 'llm1' as Hugging Face job job123 on t4-small" in text, text

    kwargs = hub.run_uv_job.call_args.kwargs
    assert kwargs["flavor"] == "t4-small" and kwargs["timeout"] == "3h"
    assert kwargs["dependencies"] == ["huggingface_hub", "torch", "transformers"]
    assert kwargs["secrets"] == {"HF_TOKEN": "hf_test_token"}
    assert kwargs["env"] == {"THESIS_HUB_REPO": "alice/llm1", "THESIS_SEED": "5"}
    script_path = hub.run_uv_job.call_args.args[0]

    # Run the exact script the job would run, as the remote machine would.
    stub_log = tmp_path / "hub.jsonl"
    env = {**remote_env(stub_log), **kwargs["env"], "HF_TOKEN": "x",
           "THESIS_RUN_DIR": str(tmp_path / "run")}
    out = subprocess.run([sys.executable, script_path], env=env, cwd=tmp_path,
                         capture_output=True, text=True, check=True).stdout
    assert "seed 5" in out and "saved to alice/llm1/model.pt" in out
    uploads = [json.loads(line) for line in stub_log.read_text().splitlines()]
    assert {"call": "upload_file", "repo_id": "alice/llm1", "path_in_repo": "model.pt"} in uploads

    # ...and feed its real output back through the tools that read job logs.
    hub.fetch_job_logs.side_effect = lambda **_: iter(out.splitlines())
    hub.inspect_job.return_value = job()
    status, _ = call("get_run_status", run_name="llm1")
    assert "RUNNING on t4-small" in status and "metric rows: 3" in status
    logs, _ = call("get_logs", run_name="llm1")
    assert "seed 5" in logs and hf_jobs.METRIC_MARKER not in logs
    assert json.loads(call("get_metrics", run_name="llm1", tail=1)[0])["step"] == 2
    for tool, args in (("plot_metrics", {"keys": "loss"}), ("rl_reward_curve", {}),
                       ("cv_training_curves", {})):
        assert "ImageContent" in call(tool, run_name="llm1", **args)[1], tool
    assert "Hugging Face job job123 on t4-small" in call("list_runs")[0]

    # same name while it is still running -> refused; nothing new is rented
    assert "still running" in call("hf_job_launch", script="pass", run_name="llm1")[0]
    assert hub.run_uv_job.call_count == 1

    hub.snapshot_download.return_value = "/local/llm1"
    assert "alice/llm1" in call("save_checkpoint", run_name="llm1")[0]
    assert hub.snapshot_download.call_args.args[0] == "alice/llm1"
    assert "already live in the Hub repo" in call("restore_checkpoint", run_name="llm1", local_filename="x")[0]
    assert "already at" in call("hf_push_run", run_name="llm1")[0]

    assert "Billing has stopped" in call("stop_run", run_name="llm1")[0]
    hub.cancel_job.assert_called_once_with(job_id="job123")


def test_job_launch_validates_input(hub):
    assert "Invalid run_name" in call("hf_job_launch", script="pass", run_name="bad/name")[0]
    assert "not valid JSON" in call("hf_job_launch", script="pass", run_name="ok", env_json="{oops")[0]
    hub.run_uv_job.assert_not_called()


def test_seed_sweep_as_parallel_jobs(hub):
    hub.run_uv_job.side_effect = [job("j1"), job("j2")]
    text, _ = call("rl_seed_sweep", script="pass", run_name="ppo", seeds="1,2", hf_flavor="t4-small")
    assert text.count(": ok") == 2, text
    seeds = [c.kwargs["env"]["THESIS_SEED"] for c in hub.run_uv_job.call_args_list]
    assert seeds == ["1", "2"]
    assert rs.store.get_run("ppo_s2")["job_id"] == "j2"


def test_hardware_and_job_listing(hub):
    hub.list_jobs_hardware.return_value = [
        JobHardwareInfo(name="cpu-basic", prettyName="CPU Basic", cpu="2 vCPU", ram="16 GB",
                        unitCostMicroUSD=167, unitCostUSD=0.000167, unitLabel="minute"),
        JobHardwareInfo(name="a10g-small", prettyName="A10G", cpu="4 vCPU", ram="15 GB",
                        accelerator={"type": "gpu", "model": "A10G", "quantity": "1", "vram": "24 GB",
                                     "manufacturer": "Nvidia"},
                        unitCostMicroUSD=16667, unitCostUSD=0.016667, unitLabel="minute"),
    ]
    table, _ = call("hf_hardware")
    assert "cpu-basic | 2 vCPU | 16 GB | - | 0.01" in table
    assert "a10g-small | 4 vCPU | 15 GB | 1x A10G (24 GB) | 1.00" in table

    hub.list_jobs.return_value = iter([])
    assert "nothing is billing" in call("hf_job_list")[0]
    hub.list_jobs.return_value = iter([job("j9")])
    assert "j9  RUNNING  t4-small" in call("hf_job_list")[0]
    assert "Canceled job j9" in call("hf_job_cancel", job_id="j9")[0]


# -- interactive runtime ------------------------------------------------------
@pytest.fixture
def started_runtime(hub, tmp_path):
    """hf_runtime_start, then the job's real command running locally as the rented machine."""
    hub.run_job.return_value = job("rt1")
    text, _ = call("hf_runtime_start", flavor="a10g-small", timeout="4h", idle_minutes=20)
    assert "Started Hugging Face runtime: job rt1 on a10g-small" in text, text
    kwargs = hub.run_job.call_args.kwargs
    assert kwargs["expose"] == [hf_jobs.RUNTIME_PORT] and kwargs["timeout"] == "4h"
    assert kwargs["image"] == config.HF_RUNTIME_IMAGE
    assert kwargs["env"]["THESIS_IDLE_MINUTES"] == "20"
    assert set(kwargs["secrets"]) == {"JUPYTER_TOKEN", "HF_TOKEN"}

    procs = []

    def boot(**overrides):
        port = free_port()
        stub_log = tmp_path / f"hub-{port}.jsonl"
        env = {**remote_env(stub_log), **kwargs["env"], **kwargs["secrets"],
               "THESIS_PORT": str(port), "THESIS_ROOT": str(tmp_path / f"root-{port}"),
               "THESIS_WATCH_SECONDS": "1", "JOB_ID": "rt1", **overrides}
        proc = subprocess.Popen([sys.executable, *kwargs["command"][1:]], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        procs.append(proc)
        return proc, f"http://127.0.0.1:{port}", env, stub_log

    yield boot, kwargs
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=20)


def test_runtime_start_connect_use_stop(hub, started_runtime):
    boot, kwargs = started_runtime
    proc, url, env, _ = boot()

    # While Hugging Face is still allocating the machine, connect reports progress.
    hub.inspect_job.return_value = job("rt1", stage="SCHEDULING")
    assert "still allocating" in call("hf_runtime_connect", wait_seconds=0)[0]

    wait_for_jupyter(url, kwargs["secrets"]["JUPYTER_TOKEN"], proc)
    hub.inspect_job.return_value = job("rt1", status={"stage": "RUNNING", "exposeUrls": [url]})
    text, _ = call("hf_runtime_connect")
    assert "kernel" in text and env["THESIS_ROOT"] in text, text
    assert rs.jupyter.bearer == "hf_test_token"
    assert call("run_code", code="print(2 ** 10)")[0].strip() == "1024"

    # a second start is refused while one is running; a later session re-attaches
    assert "already running" in call("hf_runtime_start")[0]
    assert hub.run_job.call_count == 1
    rebuilt = rs._rehydrate()
    assert rebuilt.kernel_id == rs.jupyter.kernel_id and rebuilt.ping()
    assert "Re-attached" in call("hf_runtime_connect")[0]

    assert "Billing has stopped" in call("hf_runtime_stop")[0]
    hub.cancel_job.assert_called_once_with(job_id="rt1", token="hf_test_token")
    assert not rs.jupyter.connected and rs.store.get_kernel() == {}
    assert "No Hugging Face runtime" in call("hf_runtime_connect")[0]


def test_runtime_reports_a_job_that_ended(hub, started_runtime):
    hub.inspect_job.return_value = job("rt1", status={"stage": "ERROR", "message": "out of credits"})
    text, _ = call("hf_runtime_connect")
    assert "has ended: ERROR (out of credits)" in text
    assert rs.store.get_section("hf_runtime") == {}


def test_runtime_shuts_itself_down_when_idle(started_runtime):
    boot, kwargs = started_runtime
    proc, url, env, stub_log = boot(THESIS_IDLE_MINUTES="0.05", HF_TOKEN="remote-token")
    wait_for_jupyter(url, kwargs["secrets"]["JUPYTER_TOKEN"], proc)
    runs = os.path.join(env["THESIS_ROOT"], "thesis_runs", "exp")
    os.makedirs(runs)
    open(os.path.join(runs, "metrics.jsonl"), "w").write("{}\n")

    assert proc.wait(timeout=40) == 0, "an idle runtime must exit so the job stops billing"
    assert "shutting down to stop billing" in proc.stdout.read()
    archived = [json.loads(line) for line in stub_log.read_text().splitlines()]
    upload = next(c for c in archived if c["call"] == "upload_folder")
    assert upload["repo_id"] == "alice/thesis-mcp-archive" and "exp/metrics.jsonl" in upload["files"]


def test_runtime_stays_up_while_a_run_is_alive(started_runtime):
    boot, kwargs = started_runtime
    proc, url, env, _ = boot(THESIS_IDLE_MINUTES="0.05")
    wait_for_jupyter(url, kwargs["secrets"]["JUPYTER_TOKEN"], proc)
    run_dir = os.path.join(env["THESIS_ROOT"], "thesis_runs", "training")
    os.makedirs(run_dir)
    open(os.path.join(run_dir, "pid"), "w").write(str(os.getpid()))  # a live process
    time.sleep(12)
    assert proc.poll() is None, "must not shut down while a training run is in progress"
    os.remove(os.path.join(run_dir, "pid"))
    assert proc.wait(timeout=40) == 0


# -- Hub and Spaces -----------------------------------------------------------
def test_whoami_and_search(hub):
    text, _ = call("hf_whoami")
    assert "Logged in to Hugging Face as alice (token role: write)" in text
    assert "Can pay for compute: yes" in text

    hit = type("Hit", (), {"id": "org/model", "downloads": 10, "likes": 2, "gated": True})()
    hub.list_models.return_value = iter([hit])
    assert "org/model  (downloads 10, likes 2, gated)" in call("hf_search", query="qwen")[0]
    assert hub.list_models.call_args.kwargs == {"search": "qwen", "sort": "downloads", "limit": 10}
    hub.list_datasets.return_value = iter([])
    assert "No datasets match" in call("hf_search", query="zzz", kind="dataset")[0]
    assert "kind must be" in call("hf_search", query="x", kind="space")[0]


def test_upload_and_download(hub, tmp_path):
    folder = tmp_path / "ckpt"
    folder.mkdir()
    (folder / "a.bin").write_text("x")
    text, _ = call("hf_upload", local_path=str(folder), repo_id="alice/m")
    assert text.endswith("https://huggingface.co/alice/m")
    hub.create_repo.assert_called_once_with("alice/m", repo_type="model", private=True,
                                            exist_ok=True, token="hf_test_token")
    assert hub.upload_folder.call_args.kwargs["folder_path"] == str(folder)

    call("hf_upload", local_path=str(folder / "a.bin"), repo_id="alice/d", repo_type="dataset")
    assert hub.upload_file.call_args.kwargs["path_in_repo"] == "a.bin"
    assert "No such local path" in call("hf_upload", local_path="/nope", repo_id="alice/m")[0]

    hub.hf_hub_download.return_value = "/x/config.json"
    assert "/x/config.json" in call("hf_download", repo_id="org/m", local_dir=str(tmp_path),
                                    filename="config.json")[0]
    hub.snapshot_download.return_value = "/x"
    assert "org/m -> /x" in call("hf_download", repo_id="org/m", local_dir=str(tmp_path))[0]


def test_spaces(hub):
    running = SpaceRuntime({"stage": "RUNNING", "hardware": {"current": "t4-small", "requested": "t4-small"},
                            "gcTimeout": 1800})
    hub.get_space_runtime.return_value = running
    hub.space_info.return_value = type("Info", (), {"host": "https://alice-lab.hf.space", "subdomain": "alice-lab"})()
    text, _ = call("hf_space_status", space_id="alice/lab")
    assert "alice/lab: RUNNING on t4-small, sleeps after 30 idle minutes" in text
    assert "https://alice-lab.hf.space" in text

    hub.request_space_hardware.return_value = SpaceRuntime(
        {"stage": "RUNNING", "hardware": {"current": "t4-small", "requested": "a10g-small"}})
    assert "switching to a10g-small" in call("hf_space_hardware", space_id="alice/lab",
                                             hardware="a10g-small", sleep_minutes=15)[0]
    assert hub.request_space_hardware.call_args.kwargs["sleep_time"] == 900
    assert "Unknown hardware" in call("hf_space_hardware", space_id="alice/lab", hardware="rtx9999")[0]

    hub.pause_space.return_value = SpaceRuntime({"stage": "PAUSED", "hardware": {"current": None}})
    assert "PAUSED" in call("hf_space_pause", space_id="alice/lab")[0]
    hub.restart_space.return_value = running
    assert "RUNNING" in call("hf_space_restart", space_id="alice/lab")[0]


# -- failures say what to do --------------------------------------------------
def _http_error(status):
    response = requests.Response()
    response.status_code = status
    response.request = requests.Request("POST", "https://huggingface.co/api/jobs").prepare()
    return HfHubHTTPError(f"{status} error", response=response)


def test_api_errors_carry_a_hint(hub):
    hub.run_uv_job.side_effect = _http_error(402)
    with pytest.raises(Exception, match="add credits at https://huggingface.co/settings/billing"):
        call("hf_job_launch", script="pass", run_name="broke")
    assert rs.store.get_run("broke") is None  # a failed launch leaves no phantom run

    hub.whoami.side_effect = _http_error(401)
    with pytest.raises(Exception, match="token is missing or invalid"):
        call("hf_whoami")


def test_missing_login_is_explained(monkeypatch):
    monkeypatch.setattr(hf, "get_token", lambda: None)
    with pytest.raises(Exception, match="No Hugging Face token found"):
        call("hf_job_list")
    with pytest.raises(Exception, match="No Hugging Face token found"):
        call("hf_runtime_start")


def test_jupyter_token_is_derived_not_stored(hub):
    hub.run_job.return_value = job("rt2")
    call("hf_runtime_start")
    secret = hub.run_job.call_args.kwargs["secrets"]["JUPYTER_TOKEN"]
    saved = rs.store.get_section("hf_runtime")
    assert secret == hf.jupyter_token(saved["nonce"])
    on_disk = open(rs.store.path).read()
    assert secret not in on_disk and "hf_test_token" not in on_disk
