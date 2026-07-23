"""Offline smoke tests — no runtime/network required.

Verifies the tools register cleanly and the local state store behaves.
"""

import asyncio

from thesis_mcp import server
from thesis_mcp.connectors.store import RunStore


def test_all_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        # core
        "connect_runtime", "runtime_status", "run_code", "upload_file", "download_file",
        "fetch_image", "launch_training", "get_run_status", "get_logs", "get_metrics",
        "stop_run", "list_runs", "plot_metrics", "save_checkpoint", "restore_checkpoint",
        # notebook
        "notebook_read", "notebook_create", "notebook_add_cell", "notebook_edit_cell",
        "notebook_delete_cell", "notebook_run_cell",
        # rl
        "rl_setup", "rl_reward_curve", "rl_record_rollout", "rl_seed_sweep",
        # cv
        "cv_load_dataset", "cv_training_curves", "cv_show_predictions",
        # kaggle
        "kaggle_submit", "kaggle_submissions", "kaggle_leaderboard",
        "kaggle_competition_files", "kaggle_search_datasets",
    }
    missing = expected - names
    assert not missing, f"missing tools: {sorted(missing)}"


def test_every_tool_has_a_description():
    tools = asyncio.run(server.mcp.list_tools())
    undocumented = [t.name for t in tools if not (t.description or "").strip()]
    assert not undocumented, f"tools missing descriptions: {undocumented}"


def test_store_roundtrip(tmp_path):
    s = RunStore(str(tmp_path))
    s.new_run("r1", "/content/thesis_runs/r1")
    s.update_run("r1", status="running")
    assert s.get_run("r1")["status"] == "running"
    assert any(r["name"] == "r1" for r in s.list_runs())

    # persistence across re-open
    s2 = RunStore(str(tmp_path))
    assert s2.get_run("r1")["dir"] == "/content/thesis_runs/r1"


def test_store_kernel_memory(tmp_path):
    s = RunStore(str(tmp_path))
    s.save_kernel(url="https://x.trycloudflare.com", kernel_id="abc", contents_root="/content")
    assert RunStore(str(tmp_path)).get_kernel()["kernel_id"] == "abc"
