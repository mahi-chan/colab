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
        # hugging face: jobs and the interactive runtime
        "hf_hardware", "hf_job_launch", "hf_job_list", "hf_job_cancel",
        "hf_runtime_start", "hf_runtime_connect", "hf_runtime_stop",
        # hugging face: hub and spaces
        "hf_whoami", "hf_search", "hf_upload", "hf_download", "hf_push_run",
        "hf_space_status", "hf_space_hardware", "hf_space_pause", "hf_space_restart",
        # setup help
        "setup_guide", "example_script",
        # starting and ending Colab/Kaggle sessions
        "kaggle_runtime_start", "colab_runtime_start", "runtime_stop",
    }
    assert names == expected, f"missing {sorted(expected - names)}, unexpected {sorted(names - expected)}"


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


def test_unexpanded_mcp_json_placeholders_read_as_unset():
    """A variable missing from the shell can arrive as the literal "${VAR}" from .mcp.json."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "JUPYTER_URL": "${JUPYTER_URL}", "HF_TOKEN": "${HF_TOKEN:-}"}
    code = ("from thesis_mcp import config; import os; "
            "print(repr(config.JUPYTER_URL), os.environ.get('HF_TOKEN'))")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["''", "None"]


def test_run_names_are_validated():
    from thesis_mcp.tools.core import check_run_name

    for good in ("ppo_cartpole", "llm-v2.1", "a"):
        assert check_run_name(good) == ""
    for bad in ("", "../x", "a b", "-lead", "x/y", "trailing.", "n" * 81):
        assert check_run_name(bad), bad


def test_server_starts_over_stdio_like_claude_code_launches_it(tmp_path):
    """Start the installed `thesis-mcp` command and do a real MCP handshake with it."""
    import os
    import shutil

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command = shutil.which("thesis-mcp")
    assert command, "the thesis-mcp entry point is not installed"

    async def handshake():
        env = {**os.environ, "THESIS_STATE_DIR": str(tmp_path)}
        params = StdioServerParameters(command=command, args=[], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool("list_runs", {})
                return init, tools.tools, result

    init, tools, result = asyncio.run(handshake())
    assert init.serverInfo.name == "thesis"
    assert "Hugging Face" in (init.instructions or "")
    assert len(tools) == 54
    assert result.content[0].text == "No runs yet."
