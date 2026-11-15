"""thesis-mcp FastMCP server entrypoint.

Registers every tool group and runs over stdio (how Claude Code launches it).
"""

from mcp.server.fastmcp import FastMCP

from .tools import core, cv, hf_hub, hf_jobs, kaggle_tools, notebook, rl

INSTRUCTIONS = """\
Runs ML work (RL, CV, LLM fine-tuning, experiments, competitions) on remote GPUs:
Google Colab, Kaggle, and rented Hugging Face machines.

Get a machine first — one of:
  * Colab/Kaggle: the user runs the bootstrap cell, then `connect_runtime`.
  * Hugging Face, interactive: `hf_runtime_start(flavor)` then `hf_runtime_connect`.
    It bills per minute: call `hf_runtime_stop` when the work is done.
  * Hugging Face, one training = one machine: `hf_job_launch(script, run_name, flavor,
    timeout)`. No runtime needed; the machine stops when the script ends.
`connect_runtime` / `hf_runtime_connect` re-attach to a still-running kernel, so call
one at the start of every session.

Then:
  * quick work on the runtime: `run_code`, or edit a notebook with `notebook_*`.
  * training on the runtime: `launch_training(script, run_name)` returns immediately —
    the job runs in the background. NEVER run long training via `run_code`.
  * every run (runtime or Hugging Face job) is followed the same way: `get_run_status`,
    `get_logs`, `get_metrics`, `plot_metrics`, `stop_run`.
  * inside a training script use the injected helpers `log_metric(step, **kv)` and
    `save_checkpoint_file(path)`, and read `SEED`. Do not import them.
  * results must leave the machine before it goes away: `save_checkpoint` (to the local
    computer) or `hf_push_run` (to the Hugging Face Hub). Hugging Face jobs upload what
    `save_checkpoint_file` is given to the Hub repo `<user>/<run_name>` by themselves.
  * RL: `rl_setup`, `rl_reward_curve`, `rl_record_rollout`, `rl_seed_sweep`.
  * CV: `cv_load_dataset`, `cv_training_curves`, `cv_show_predictions`.
  * competitions: `kaggle_*` (files, submit, submissions, leaderboard).
  * Hub: `hf_whoami`, `hf_search`, `hf_upload`, `hf_download`; Spaces: `hf_space_*`.

Money: Hugging Face machines cost real money per minute. Ask the user before renting a
GPU flavor, show prices with `hf_hardware`, always set a sensible `timeout`, and use
`hf_job_list` to confirm nothing is left running.
"""

mcp = FastMCP("thesis", instructions=INSTRUCTIONS)

core.register(mcp)
notebook.register(mcp)
rl.register(mcp)
cv.register(mcp)
kaggle_tools.register(mcp)
hf_jobs.register(mcp, core.connect_impl)
hf_hub.register(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
