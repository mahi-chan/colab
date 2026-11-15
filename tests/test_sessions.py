"""Starting Colab/Kaggle sessions and pairing with them.

Google and Kaggle themselves are not reachable from a test, so their parts are stood in
for: the rendezvous service by a local server, the Kaggle API by a spec-checked mock, and
the public tunnel by a local address. Everything else is real: the exact line the user
would paste and the exact script pushed to Kaggle are executed, they start a real Jupyter
server, announce themselves, and the tools connect to them.
"""

import json
import os
import shlex
import subprocess
import sys
import time

import pytest
import requests
from conftest import call, free_port, remote_env

from gpu_bridge import config
from gpu_bridge import runtime_state as rs
from gpu_bridge.connectors import pairing
from gpu_bridge.remote import entrypoint as remote
from gpu_bridge.tools import sessions


@pytest.fixture
def machine(tmp_path):
    """Runs a command the way the remote machine would, on a local port instead of a tunnel."""
    procs = []

    def run(argv, extra_env=None):
        port = free_port()
        env = {**remote_env(tmp_path / "hub.jsonl"), "GPU_BRIDGE_PORT": str(port),
               "GPU_BRIDGE_PUBLIC_URL": f"http://127.0.0.1:{port}", "GPU_BRIDGE_ROOT": str(tmp_path / f"root-{port}"),
               "GPU_BRIDGE_WATCH_SECONDS": "1", **(extra_env or {})}
        os.makedirs(env["GPU_BRIDGE_ROOT"])
        proc = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        procs.append(proc)
        return proc, env

    yield run
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=20)


def fake_github(monkeypatch, serves_current_program: bool):
    real_get = requests.get

    def get(url, **kwargs):
        if "raw.githubusercontent.com" not in url:
            return real_get(url, **kwargs)
        if not serves_current_program:
            raise requests.ConnectionError("offline")
        response = requests.Response()
        response.status_code = 200
        response._content = pairing.entrypoint_source().encode()
        return response

    monkeypatch.setattr(sessions.requests, "get", get)


# -- the signed announcement --------------------------------------------------
def test_announcement_is_signed_and_the_topic_hides_the_code():
    code = pairing.new_code()
    line = remote.announcement(code, "https://abc.trycloudflare.com")
    assert pairing.find_announcement("noise\n" + line + "\nmore", code) == "https://abc.trycloudflare.com"
    # as it appears inside Kaggle's JSON log, with the quotes escaped
    assert pairing.find_announcement(json.dumps({"data": line}), code) == "https://abc.trycloudflare.com"
    # a different code, or a tampered address, is rejected
    assert pairing.find_announcement(line, pairing.new_code()) is None
    assert pairing.find_announcement(line.replace("abc.", "evil."), code) is None
    assert pairing.find_announcement("nothing here", code) is None
    assert code not in remote.topic_for(code)


def test_latest_valid_announcement_wins():
    code = pairing.new_code()
    text = remote.announcement(code, "https://old.trycloudflare.com") + "\n" + \
        remote.announcement(code, "https://new.trycloudflare.com")
    assert pairing.find_announcement(text, code) == "https://new.trycloudflare.com"


# -- Colab --------------------------------------------------------------------
def test_colab_one_line_pairs_without_copying_anything_back(rendezvous, machine, monkeypatch):
    fake_github(monkeypatch, serves_current_program=True)
    steps, _ = call("colab_runtime_start")
    line = next(ln for ln in steps.splitlines() if ln.startswith("!curl"))
    assert pairing.entrypoint_url() in line and "https://colab.new" in steps

    # Before the user has run the line, connecting just reports that it is waiting.
    assert "Not connected yet" in call("connect_runtime", wait_seconds=0)[0]

    # Run what the line runs: the program from the URL, with the pairing code as argument,
    # and the non-default rendezvous address the line carries.
    words = shlex.split(line.split("|", 1)[1])
    assert words[0] == f"GPU_BRIDGE_RENDEZVOUS_URL={rendezvous['url']}"
    code = words[-1]
    proc, env = machine([sys.executable, str(pairing.ENTRYPOINT_PATH), code],
                        {"GPU_BRIDGE_RENDEZVOUS_URL": rendezvous["url"]})

    text, _ = call("connect_runtime", wait_seconds=60)
    assert "kernel" in text and env["GPU_BRIDGE_ROOT"] in text, text
    assert call("run_code", code="print(6 * 7)")[0].strip() == "42"
    assert list(rendezvous["topics"]) == [remote.topic_for(code)]

    # a later session re-attaches from the state file, with no pairing step
    rebuilt = rs._rehydrate()
    assert rebuilt.token == code and rebuilt.ping()
    assert "Re-attached" in call("connect_runtime")[0]

    assert "Stopping the colab session" in call("runtime_stop")[0]
    assert proc.wait(timeout=30) == 0, "runtime_stop must end the remote program"
    assert not rs.jupyter.connected and rs.store.get_section("pairing") == {}


def test_colab_line_is_self_contained_when_github_cannot_serve_it(rendezvous, machine, monkeypatch):
    fake_github(monkeypatch, serves_current_program=False)
    steps, _ = call("colab_runtime_start")
    line = next(ln for ln in steps.splitlines() if ln.startswith("import os,base64"))
    assert "curl" not in line and len(line) < 8000, "short enough to paste"

    machine([sys.executable, "-c", line])  # exactly what the notebook cell would execute
    text, _ = call("connect_runtime", wait_seconds=60)
    assert "kernel" in text, text
    assert call("run_code", code="print('hello')")[0].strip() == "hello"


def test_state_file_is_private_and_holds_no_account_credential(rendezvous, monkeypatch):
    fake_github(monkeypatch, serves_current_program=True)
    call("colab_runtime_start")
    on_disk = open(rs.store.path).read()
    assert "hf_test_token" not in on_disk
    if os.name == "posix":
        assert oct(os.stat(rs.store.path).st_mode & 0o777) == "0o600"


# -- Kaggle -------------------------------------------------------------------
def pushed(kaggle):
    folder = kaggle.kernels_push.call_args.args[0]
    meta = json.load(open(os.path.join(folder, "kernel-metadata.json")))
    return meta, os.path.join(folder, meta["code_file"])


def test_kaggle_session_starts_and_pairs_through_its_own_log(kaggle, machine):
    from slugify import slugify  # the library Kaggle uses to turn a title into a slug

    text, _ = call("kaggle_runtime_start", competition="titanic", datasets="owner/data, other/set",
                   idle_minutes=20, max_hours=2)
    assert "Started a Kaggle GPU session (https://www.kaggle.com/code/alice/gpu-bridge-runtime)" in text
    assert kaggle.kernels_push.call_args.kwargs == {"timeout": "7200"}
    meta, script = pushed(kaggle)
    assert meta["id"] == "alice/gpu-bridge-runtime" and slugify(meta["title"]) == "gpu-bridge-runtime"
    assert meta["enable_gpu"] is True and meta["enable_internet"] is True and meta["is_private"] is True
    assert meta["competition_sources"] == ["titanic"] and meta["dataset_sources"] == ["owner/data", "other/set"]
    assert (meta["kernel_type"], meta["language"]) == ("script", "python")

    # Kaggle is still queueing: connect reports progress and nothing breaks.
    kaggle.kernels_status.return_value.status.name = "QUEUED"
    kaggle.kernels_status.return_value.failure_message = ""
    kaggle.kernels_logs.return_value = ""
    assert "still starting" in call("connect_runtime", wait_seconds=0)[0]
    assert "already running" in call("kaggle_runtime_start")[0]
    assert kaggle.kernels_push.call_count == 1

    # Run the pushed script as Kaggle would. The rendezvous service is unreachable in this
    # test, so the address can only arrive through the session log read from the Kaggle API.
    proc, env = machine([sys.executable, script])
    log = []
    kaggle.kernels_status.return_value.status.name = "RUNNING"

    def read_log(_ref):
        os.set_blocking(proc.stdout.fileno(), False)
        log.append(proc.stdout.read() or "")
        return json.dumps([{"stream_name": "stdout", "data": line} for line in "".join(log).splitlines()])

    kaggle.kernels_logs.side_effect = read_log
    text, _ = call("connect_runtime", wait_seconds=60)
    assert "kernel" in text and env["GPU_BRIDGE_ROOT"] in text, text
    assert rs.store.get_kernel()["platform"] == "kaggle"
    assert call("run_code", code="import os; print(os.environ['GPU_BRIDGE_IDLE_MINUTES'])")[0].strip() == "20"

    stop, _ = call("runtime_stop")
    assert "Stopping the kaggle session" in stop and "/kaggle/working" in stop
    assert proc.wait(timeout=30) == 0


def test_kaggle_session_that_fails_is_reported_with_its_log(kaggle):
    call("kaggle_runtime_start", gpu=False)
    assert pushed(kaggle)[0]["enable_gpu"] is False
    kaggle.kernels_status.return_value.status.name = "ERROR"
    kaggle.kernels_status.return_value.failure_message = "Internet access requires phone verification"
    kaggle.kernels_logs.return_value = "Traceback ...\nurlopen error"
    text, _ = call("connect_runtime", wait_seconds=0)
    assert "ended before connecting: ERROR" in text and "phone verification" in text and "urlopen error" in text
    assert rs.store.get_section("pairing") == {}


def test_kaggle_problems_are_explained(kaggle):
    kaggle.kernels_push.return_value.error = "Maximum weekly GPU quota reached"
    assert "Maximum weekly GPU quota reached" in call("kaggle_runtime_start")[0]
    kaggle.kernels_push.return_value.error = None
    kaggle.kernels_push.return_value.invalid_competition_sources = ["nope"]
    assert "could not attach" in call("kaggle_runtime_start", competition="nope")[0]


def test_kaggle_without_login_says_how_to_log_in():
    text, _ = call("kaggle_runtime_start")
    assert "login kaggle" in text
    assert rs.store.get_section("pairing") == {}
    assert "No Colab/Kaggle session" in call("runtime_stop")[0]


def test_kaggle_library_keys_we_rely_on(kaggle):
    """The credential names forwarded to a runtime must match what the Kaggle library uses."""
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        from kaggle.api.kaggle_api_extended import KaggleApi
    from gpu_bridge.connectors import kaggle_api

    assert (KaggleApi.CONFIG_NAME_USER, KaggleApi.CONFIG_NAME_KEY, KaggleApi.CONFIG_NAME_TOKEN) == \
        ("username", "key", "token")
    assert kaggle_api.forward_env() == {"KAGGLE_USERNAME": "alice", "KAGGLE_KEY": "kaggle-key"}
    kaggle.config_values["token"] = "KGAT_x"
    assert kaggle_api.forward_env() == {"KAGGLE_API_TOKEN": "KGAT_x"}


# -- the tunnel ---------------------------------------------------------------
def test_tunnel_address_is_read_from_the_tunnel_program(rendezvous, tmp_path):
    """With a stand-in tunnel program, the remote side finds the address and announces it."""
    root = tmp_path / "root"
    root.mkdir()
    tunnel = root / ".cloudflared"
    tunnel.write_text("#!/bin/sh\necho 'INF Requesting new quick Tunnel on api.trycloudflare.com...'\n"
                      "echo 'INF |  https://calm-river-demo.trycloudflare.com  |'\nsleep 600\n")
    tunnel.chmod(0o755)
    code = pairing.new_code()
    env = {**remote_env(tmp_path / "hub.jsonl"), "GPU_BRIDGE_ROOT": str(root), "GPU_BRIDGE_WATCH_SECONDS": "1",
           "GPU_BRIDGE_RENDEZVOUS_URL": rendezvous["url"]}
    proc = subprocess.Popen([sys.executable, str(pairing.ENTRYPOINT_PATH), code], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(120):
            if pairing.from_rendezvous(code):
                break
            time.sleep(0.5)
        assert pairing.from_rendezvous(code) == "https://calm-river-demo.trycloudflare.com"
    finally:
        proc.terminate()
        proc.wait(timeout=20)


def test_run_by_hand_it_prints_the_address_and_a_token(tmp_path):
    """Without a pairing code the program still works: it prints what to give the assistant."""
    port = free_port()
    env = {**remote_env(tmp_path / "hub.jsonl"), "GPU_BRIDGE_ROOT": str(tmp_path), "GPU_BRIDGE_PORT": str(port),
           "GPU_BRIDGE_PUBLIC_URL": f"http://127.0.0.1:{port}", "GPU_BRIDGE_WATCH_SECONDS": "1"}
    proc = subprocess.Popen([sys.executable, str(pairing.ENTRYPOINT_PATH)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        seen = ""
        for _ in range(400):
            seen += proc.stdout.readline()
            if "JUPYTER_TOKEN=" in seen:
                break
        url = seen.split('JUPYTER_URL="')[1].split('"')[0]
        token = seen.split('JUPYTER_TOKEN="')[1].split('"')[0]
        assert "kernel" in call("connect_runtime", url=url, token=token)[0]
    finally:
        proc.terminate()
        proc.wait(timeout=20)


def test_doctor_reports_every_platform(kaggle):
    from gpu_bridge import doctor

    report = doctor.endpoints()
    assert "Kaggle: logged in as alice" in report and "Hugging Face: token found" in report
    assert "Colab: no setup" in report
    assert config.RENDEZVOUS_URL  # the fixture keeps tests off the real service
