"""Integration tests: every runtime tool against a real Jupyter server.

The server stands in for the remote machine (Colab, Kaggle or Hugging Face); what is
exercised here is the real kernel protocol, file API and background-process handling.
"""

import json
import os
import time

from conftest import call, wait_until_stopped

import pytest

from thesis_mcp import config
from thesis_mcp import runtime_state as rs
from thesis_mcp.connectors import hf

TRAIN = '''
import os, time
for i in range(4):
    log_metric(step=i, loss=1.0 / (i + 1), reward=i * 10.0)
    time.sleep(0.2)
os.makedirs("adapter", exist_ok=True)
open("adapter/weights.bin", "w").write("w" * 10)
save_checkpoint_file("adapter")                      # a folder
open("model.pt", "w").write("weights")
save_checkpoint_file("model.pt")                     # a file
print("done seed", SEED)
'''


def test_connect_run_code_and_reattach(runtime):
    text, _ = call("run_code", code="x = 20 + 22\nprint(x)")
    assert text.strip() == "42"
    text, _ = call("run_code", code="print(x)")  # kernel state persists between calls
    assert text.strip() == "42"
    text, _ = call("connect_runtime")
    assert "Re-attached" in text
    assert "python" in call("runtime_status")[0]


def test_run_code_returns_images(runtime):
    code = ("import base64\nfrom IPython.display import Image, display\n"
            "display(Image(data=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE"
            "QVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='), format='png'))")
    _, kinds = call("run_code", code=code)
    assert "ImageContent" in kinds


def test_run_code_reports_errors_and_recovers_from_timeout(runtime):
    text, _ = call("run_code", code="1/0")
    assert "ZeroDivisionError" in text
    text, _ = call("run_code", code="import time; time.sleep(30)", timeout=3)
    assert "timed out" in text
    text, _ = call("run_code", code="print('alive')")
    assert text.strip() == "alive"


def test_training_run_lifecycle(runtime):
    text, _ = call("launch_training", script=TRAIN, run_name="demo", env_json='{"THESIS_SEED": "7"}')
    assert "Launched" in text, text
    status = wait_until_stopped("demo")
    assert "metric rows: 4" in status

    assert "done seed 7" in call("get_logs", run_name="demo")[0]
    last = json.loads(call("get_metrics", run_name="demo", tail=1)[0])
    assert last["step"] == 3 and last["reward"] == 30.0

    for tool, args in (("plot_metrics", {"keys": "loss,reward"}), ("rl_reward_curve", {}),
                       ("cv_training_curves", {})):
        _, kinds = call(tool, run_name="demo", **args)
        assert "ImageContent" in kinds, tool

    assert "demo: stopped" in call("list_runs")[0]

    # single file, then the whole checkpoints/ dir (file + folder) as a zip
    assert "Saved" in call("save_checkpoint", run_name="demo", filename="model.pt")[0]
    local = os.path.join(config.STATE_DIR, "checkpoints", "demo")
    assert open(os.path.join(local, "model.pt")).read() == "weights"
    assert "Saved" in call("save_checkpoint", run_name="demo")[0]
    assert os.path.getsize(os.path.join(local, "checkpoints.zip")) > 0
    assert "Restored" in call("restore_checkpoint", run_name="demo", local_filename="model.pt")[0]
    text, _ = call("run_code", code=f"import os; print(sorted(os.listdir({rs.run_root()!r} + '/demo/checkpoints')))")
    assert "adapter" in text and "model.pt" in text


def test_requirements_install_inside_the_run(runtime):
    # "pip" itself is always installable; proves the install step runs before the script.
    text, _ = call("launch_training", script="print('after install')", run_name="req", requirements="pip")
    assert "Launched" in text, text
    wait_until_stopped("req")
    assert "after install" in call("get_logs", run_name="req")[0]


def test_stop_run_and_no_clobber(runtime):
    forever = "import time\nwhile True:\n    time.sleep(1)"
    assert "Launched" in call("launch_training", script=forever, run_name="forever")[0]
    time.sleep(1)
    assert "RUNNING" in call("get_run_status", run_name="forever")[0]
    assert "still running" in call("launch_training", script="pass", run_name="forever")[0]
    call("stop_run", run_name="forever")
    wait_until_stopped("forever", seconds=20)


def test_seed_sweep_on_runtime(runtime):
    text, _ = call("rl_seed_sweep", script=TRAIN, run_name="sweep", seeds="1,2")
    assert text.count(": ok") == 2, text
    for seed in (1, 2):
        wait_until_stopped(f"sweep_s{seed}")
        assert f"done seed {seed}" in call("get_logs", run_name=f"sweep_s{seed}")[0]


def test_bad_run_name_is_rejected(runtime):
    assert "Invalid run_name" in call("launch_training", script="pass", run_name="../escape")[0]
    assert "Invalid run_name" in call("launch_training", script="pass", run_name="has space")[0]


def test_files_roundtrip(runtime, tmp_path):
    src = tmp_path / "data.bin"
    src.write_bytes(bytes(range(256)) * 40)
    assert "Uploaded" in call("upload_file", local_path=str(src), remote_path="files/in/data.bin")[0]
    dst = tmp_path / "back" / "data.bin"
    assert "Downloaded" in call("download_file", remote_path="files/in/data.bin", local_path=str(dst))[0]
    assert dst.read_bytes() == src.read_bytes()


def test_notebook_editing(runtime):
    path = "notebooks/exp/analysis.ipynb"
    call("notebook_create", path=path)
    call("notebook_add_cell", path=path, source="# Analysis", cell_type="markdown")
    call("notebook_add_cell", path=path, source="print(1)")
    call("notebook_edit_cell", path=path, index=1, source="print('edited')")
    text, _ = call("notebook_run_cell", path=path, index=1)
    assert "edited" in text
    listing, _ = call("notebook_read", path=path)
    assert "2 cells" in listing and "markdown" in listing
    call("notebook_delete_cell", path=path, index=0)
    assert "1 cells" in call("notebook_read", path=path)[0]


def test_cv_show_predictions_and_fetch_image(runtime):
    code = ("import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
            "plt.figure(); plt.plot([0, 1], [1, 0]); plt.savefig(OUT); print('saved')")
    text, kinds = call("cv_show_predictions", inference_code=code, out="viz/preds.png")
    assert "ImageContent" in kinds, text
    _, kinds = call("fetch_image", remote_path="viz/preds.png")
    assert "ImageContent" in kinds


def test_rl_record_rollout(runtime):
    call("launch_training", script="pass", run_name="policy")
    wait_until_stopped("policy")
    rollout = "import numpy as np\nframes = [np.full((16, 16, 3), i * 20, dtype='uint8') for i in range(8)]"
    text, kinds = call("rl_record_rollout", run_name="policy", rollout_code=rollout)
    assert "ImageContent" in kinds, text
    assert "frames 8" in text


def test_hf_push_run_from_runtime(runtime):
    call("launch_training", script=TRAIN, run_name="pushme")
    wait_until_stopped("pushme")

    # with no login anywhere the tool explains what to do
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(hf, "get_token", lambda: None)
        assert "No Hugging Face login" in call("hf_push_run", run_name="pushme", repo_id="alice/pushme")[0]

    # this computer's login is used for the upload; nothing is set up on the runtime
    text, _ = call("hf_push_run", run_name="pushme")
    assert "Pushed run 'pushme' to https://huggingface.co/alice/pushme" in text, text
    calls = [json.loads(line) for line in runtime["stub_log"].read_text().splitlines()]
    upload = next(c for c in calls if c["call"] == "upload_folder" and c["repo_id"] == "alice/pushme")
    assert "checkpoints/model.pt" in upload["files"] and "metrics.jsonl" in upload["files"]
    history, _ = call("run_code", code="print(('hf_test' + '_token') in repr(In))")
    assert history.strip() == "False", "the login must not be left in the kernel's history"


def test_hf_authenticated_connection(runtime):
    """Hugging Face Spaces/Jobs mode: HF token in the Authorization header, Jupyter token in the query."""
    text, _ = call("connect_runtime", url=runtime["url"], token=runtime["token"], hf_auth=True)
    assert "kernel" in text, text
    assert rs.jupyter._headers == {"Authorization": "Bearer hf_test_token"}
    assert call("run_code", code="print(6 * 7)")[0].strip() == "42"
    assert rs.store.get_kernel()["auth"] == "hf"

    # a new process must rebuild the same connection from the state file + environment
    os.environ["JUPYTER_TOKEN"] = runtime["token"]
    config.JUPYTER_TOKEN = runtime["token"]
    try:
        rebuilt = rs._rehydrate()
    finally:
        os.environ.pop("JUPYTER_TOKEN")
        config.JUPYTER_TOKEN = ""
    assert rebuilt.bearer == "hf_test_token" and rebuilt.kernel_id == rs.jupyter.kernel_id
    assert rebuilt.ping()


def test_wrong_token_is_reported_not_connected(jupyter_server):
    rs.jupyter.configure(jupyter_server["url"], "wrong-token")
    assert rs.jupyter.ping() is False


def test_tools_explain_missing_runtime():
    text, _ = call("connect_runtime")
    assert "No runtime yet" in text and "kaggle_runtime_start" in text
    assert "Not connected" in call("runtime_status")[0]


def test_kaggle_tools_build_the_right_commands(runtime):
    text, _ = call("kaggle_submit", competition="titanic", file="sub.csv", message="first try")
    assert "KAGGLE competitions submit -c titanic -f sub.csv -m first try" in text
    assert "KAGGLE competitions leaderboard -c titanic --show" in call("kaggle_leaderboard", competition="titanic")[0]
    assert "KAGGLE competitions submissions -c titanic" in call("kaggle_submissions", competition="titanic")[0]
    assert "KAGGLE competitions files -c titanic" in call("kaggle_competition_files", competition="titanic")[0]
    assert "KAGGLE datasets list -s mnist" in call("kaggle_search_datasets", query="mnist")[0]


def test_cv_load_dataset_downloads_and_unzips(runtime):
    text, _ = call("cv_load_dataset", ref="titanic", dest="data/titanic", kind="competition")
    assert "KAGGLE competitions download -c titanic -p data/titanic" in text
    assert "train.csv" in text and "LOGIN none" in text
    text, _ = call("cv_load_dataset", ref="owner/set", dest="data/set")
    assert "KAGGLE datasets download -d owner/set -p data/set" in text


def test_cv_load_dataset_lends_the_local_kaggle_login(runtime, kaggle):
    text, _ = call("cv_load_dataset", ref="owner/set", dest="data/lent")
    assert "LOGIN alice" in text, "the runtime's Kaggle command runs with this computer's login"
    history, _ = call("run_code", code="print(('kaggle' + '-key') in repr(In))")
    assert history.strip() == "False", "the login must not be left in the kernel's history"


def test_kaggle_tools_run_locally_when_logged_in(runtime, kaggle, monkeypatch, tmp_path):
    from thesis_mcp.connectors import kaggle_api

    calls = []
    monkeypatch.setattr(kaggle_api, "cli", lambda args, timeout=300, cwd=None: calls.append(args) or "ok")
    assert call("kaggle_leaderboard", competition="titanic")[0] == "ok"
    assert calls[-1] == ["competitions", "leaderboard", "-c", "titanic", "--show"]

    # a submission file that lives on the runtime is fetched, then submitted from here
    call("run_code", code="open('submission.csv', 'w').write('id,label\\n1,0\\n')")
    call("kaggle_submit", competition="titanic", file="submission.csv", message="try 1")
    local_file = calls[-1][calls[-1].index("-f") + 1]
    assert open(local_file).read() == "id,label\n1,0\n"


def test_kaggle_tools_without_login_or_runtime_say_how_to_log_in():
    assert "login kaggle" in call("kaggle_leaderboard", competition="titanic")[0]
