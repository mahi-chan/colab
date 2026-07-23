# thesis-mcp — working notes for Claude Code

This repo IS an MCP server that you (Claude Code) use to run ML thesis experiments
(reinforcement learning or computer vision) on a **Google Colab / Kaggle GPU**. The
server is defined here in `src/thesis_mcp/`; when it's registered, its tools appear as
`thesis` tools. This file is your memory across `/clear` — read it first each session.

## Every session, do this first
1. Make sure a runtime is up: the user runs `runtime/colab_bootstrap.py` (or
   `runtime/kaggle_bootstrap.py`) in a Colab/Kaggle cell and exports the printed
   `JUPYTER_URL` / `JUPYTER_TOKEN` before launching Claude Code.
2. Call **`connect_runtime`**. It re-attaches to an already-running kernel if one
   exists (so a fresh session after `/clear` keeps the same runtime and runs).
3. `runtime_status` to confirm the GPU.

## The one rule that matters: training is fire-and-poll
Colab/Kaggle disconnect, and each tool call is short. So:
- **Never** run long training with `run_code` — it will hit the timeout.
- Use **`launch_training(script, run_name)`** → returns immediately (job runs in the
  background on the VM). Then poll `get_run_status` / `get_logs` / `get_metrics` and
  visualize with `plot_metrics`.
- Inside a training `script`, these are injected — do not import them:
  `log_metric(step, **kv)`, `save_checkpoint_file(path)`, `THESIS_RUN_DIR`, `SEED`.
- Checkpoints live in the run's `checkpoints/` dir on the VM. Call **`save_checkpoint`**
  to copy them to the user's local machine so they survive the VM shutting down;
  `restore_checkpoint` puts them back on a fresh runtime.

## Tool map
- **Runtime/exec:** `connect_runtime`, `runtime_status`, `run_code`, `upload_file`,
  `download_file`, `fetch_image`.
- **Training:** `launch_training`, `get_run_status`, `get_logs`, `get_metrics`,
  `stop_run`, `list_runs`, `plot_metrics`, `save_checkpoint`, `restore_checkpoint`.
- **Notebook editing (edit Colab cells):** `notebook_create`, `notebook_read`,
  `notebook_add_cell`, `notebook_edit_cell`, `notebook_delete_cell`, `notebook_run_cell`.
- **RL:** `rl_setup`, `rl_reward_curve`, `rl_record_rollout`, `rl_seed_sweep`.
- **CV:** `cv_load_dataset`, `cv_training_curves`, `cv_show_predictions`.
- **Kaggle:** `kaggle_search_datasets`, `kaggle_competition_files`, `kaggle_submit`,
  `kaggle_submissions`, `kaggle_leaderboard`.

## Recipes
**RL** (see `examples/rl_cartpole.py`):
`rl_setup("classic-control")` → `launch_training(open('examples/rl_cartpole.py').read(),
"ppo_cartpole", requirements="gymnasium[classic-control] stable-baselines3")` → poll →
`rl_reward_curve("ppo_cartpole")` → `rl_record_rollout(...)`. Report several seeds with
`rl_seed_sweep(script, "ppo_cartpole", "0,1,2")`.

**CV** (see `examples/cv_mnist.py`):
optionally `cv_load_dataset("owner/slug")` or `cv_load_dataset("<competition>", kind="competition")`
→ `launch_training(open('examples/cv_mnist.py').read(), "mnist_cnn", requirements="torch torchvision")`
→ poll → `cv_training_curves("mnist_cnn")` → `cv_show_predictions(code)` → `kaggle_submit(...)`.

## Editing this server
Tools are grouped in `src/thesis_mcp/tools/{core,notebook,rl,cv,kaggle_tools}.py`; each has
`register(mcp)`, wired in `src/thesis_mcp/server.py`. The runtime connection + run registry
are singletons in `src/thesis_mcp/runtime_state.py`. After changing tool code, the user must
restart the MCP (relaunch Claude Code or `/mcp` reconnect). Run `uv run pytest` for the
offline smoke tests.

## Never
- Never commit secrets. `JUPYTER_TOKEN` and Kaggle keys come from the environment only;
  `.thesis-mcp/`, `kaggle.json`, and `.env` are git-ignored.
- Never assume a runtime is alive after a long gap — re-run `connect_runtime` / `runtime_status`.
