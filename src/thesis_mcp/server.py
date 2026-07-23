"""thesis-mcp FastMCP server entrypoint.

Registers every tool group and runs over stdio (how Claude Code launches it).
"""

from mcp.server.fastmcp import FastMCP

from .tools import core, cv, kaggle_tools, notebook, rl

INSTRUCTIONS = """\
Drives a Google Colab / Kaggle GPU runtime for ML thesis work (RL & CV).

Start every session by calling `connect_runtime` (it re-attaches to an already
running kernel if one exists). Then:
  * quick work: `run_code`, or edit a notebook with `notebook_*`.
  * training: `launch_training(script, run_name)` returns immediately — the job runs
    in the background on the VM. Poll with `get_run_status` / `get_logs` / `get_metrics`
    and visualize with `plot_metrics`. NEVER run long training via `run_code`.
  * inside a training script use the injected helpers `log_metric(step, **kv)` and
    `save_checkpoint_file(path)`, and read `SEED`.
  * checkpoints: `save_checkpoint` copies them to the local machine so they survive the
    VM shutting down; `restore_checkpoint` puts them back.
  * RL: `rl_setup`, `rl_reward_curve`, `rl_record_rollout`, `rl_seed_sweep`.
  * CV: `cv_load_dataset`, `cv_training_curves`, `cv_show_predictions`, and `kaggle_*`
    for competition submission / leaderboard.
"""

mcp = FastMCP("thesis", instructions=INSTRUCTIONS)

core.register(mcp)
notebook.register(mcp)
rl.register(mcp)
cv.register(mcp)
kaggle_tools.register(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
