# gpu-bridge — working notes for Claude Code

This repo IS an MCP server that you (Claude Code) use to run ML work — RL, CV, LLM
fine-tuning, experiments, competitions — on remote GPUs: **Google Colab, Kaggle, and
rented Hugging Face machines**. The server is defined in `src/gpu_bridge/`; when it is
registered, its tools appear as `gpu-bridge` tools. This file is your memory across
`/clear` — read it first each session.

## Every session, get a machine first
Pick one, depending on what the user is using:

| Where | How |
|-------|-----|
| Kaggle (free) | **`kaggle_runtime_start`**, then **`connect_runtime`** (repeat until it is up). Automatic once the user has run `gpu-bridge login kaggle`. |
| Colab (free) | **`colab_runtime_start`** returns one line; the user runs it in a Colab cell; then **`connect_runtime`**. Nothing is copied back. |
| Hugging Face, interactive (paid) | **`hf_runtime_start(flavor, timeout)`**, then **`hf_runtime_connect`** (repeat until ready). **`hf_runtime_stop`** when done. |
| Hugging Face, one training per machine (paid) | **`hf_job_launch(script, run_name, flavor, timeout)`**. No runtime needed. |
| A JupyterLab Space the user already has | `connect_runtime(url, token, hf_auth=True)`. |

`connect_runtime` (no arguments) and `hf_runtime_connect` re-attach to a runtime that is
still up, so after `/clear` call the right one again and carry on. `runtime_status`
confirms the GPU. `runtime_stop` ends a Colab/Kaggle session. If the user asks how to set
something up, `setup_guide(platform)` has the steps.

## The one rule that matters: training is fire-and-poll
Remote machines disconnect, and each tool call is short. So:
- **Never** run long training with `run_code` — it will hit the timeout.
- On a connected runtime use **`launch_training(script, run_name)`**; on its own Hugging
  Face machine use **`hf_job_launch`**. Both return immediately.
- Follow any run the same way: `get_run_status`, `get_logs`, `get_metrics`,
  `plot_metrics`, `stop_run`. `list_runs` shows what exists.
- Inside a training `script`, these are injected — do not import them:
  `log_metric(step, **kv)`, `save_checkpoint_file(path)` (file or folder),
  `GPU_BRIDGE_RUN_DIR`, `SEED`. The same script runs on every backend.

## Results must leave the machine
Every remote disk is temporary.
- Runtime run: `save_checkpoint` (download to the user's computer) or `hf_push_run`
  (upload straight to a private Hub repo). `restore_checkpoint` puts a file back.
- Hugging Face job: `save_checkpoint_file` uploads to the private Hub repo
  `<user>/<run_name>` by itself; `save_checkpoint` downloads from there.
- A Hugging Face runtime that shuts down for idleness first archives its runs folder to
  `<user>/gpu-bridge-archive`. A timeout or `hf_runtime_stop` does **not** — push first.

## Money (Hugging Face only)
Hugging Face machines bill per minute until they end.
- Ask the user before renting a GPU flavor. `hf_hardware` lists flavors and prices.
- Always pass a sensible `timeout`. An interactive runtime also stops after
  `idle_minutes` with nothing running.
- Before ending a session, `hf_job_list` must show nothing unexpected running.
- `hf_whoami` checks the login and whether the account can pay.

## Tool map
- **Get a machine:** `kaggle_runtime_start`, `colab_runtime_start`, `connect_runtime`,
  `runtime_stop`, `runtime_status`.
- **Run code and files:** `run_code`, `upload_file`, `download_file`, `fetch_image`.
- **Runs:** `launch_training`, `get_run_status`, `get_logs`, `get_metrics`, `stop_run`,
  `list_runs`, `plot_metrics`, `save_checkpoint`, `restore_checkpoint`.
- **Notebook cells:** `notebook_create`, `notebook_read`, `notebook_add_cell`,
  `notebook_edit_cell`, `notebook_delete_cell`, `notebook_run_cell`.
- **RL:** `rl_setup`, `rl_reward_curve`, `rl_record_rollout`, `rl_seed_sweep`.
- **CV:** `cv_load_dataset`, `cv_training_curves`, `cv_show_predictions`.
- **Kaggle competitions:** `kaggle_search_datasets`, `kaggle_competition_files`,
  `kaggle_submit`, `kaggle_submissions`, `kaggle_leaderboard`. They use the Kaggle login
  on this computer and need no runtime (submitting fetches the file from the runtime).
- **Hugging Face compute:** `hf_hardware`, `hf_job_launch`, `hf_job_list`,
  `hf_job_cancel`, `hf_runtime_start`, `hf_runtime_connect`, `hf_runtime_stop`.
- **Setup help:** `setup_guide(platform)` returns the steps to connect Colab, Kaggle,
  Hugging Face or a Space; `example_script(name)` returns the example training scripts.
- **Hugging Face Hub / Spaces:** `hf_whoami`, `hf_search`, `hf_upload`, `hf_download`,
  `hf_push_run`, `hf_space_status`, `hf_space_hardware`, `hf_space_pause`,
  `hf_space_restart`.

## Recipes
**LLM fine-tune** (see `examples/llm_lora_finetune.py`):
`hf_job_launch(open('examples/llm_lora_finetune.py').read(), "smollm-quotes",
flavor="t4-small", timeout="1h", requirements="torch transformers peft datasets accelerate",
env_json='{"BASE_MODEL": "...", "MAX_STEPS": "300"}')` → poll → `plot_metrics(run, "loss")`.
The adapter lands in the Hub repo `<user>/smollm-quotes`.

**RL** (see `examples/rl_cartpole.py`):
`rl_setup("classic-control")` → `launch_training(open('examples/rl_cartpole.py').read(),
"ppo_cartpole", requirements="gymnasium[classic-control] stable-baselines3")` → poll →
`rl_reward_curve("ppo_cartpole")` → `rl_record_rollout(...)`. Several seeds:
`rl_seed_sweep(script, "ppo_cartpole", "0,1,2")`; add `hf_flavor="t4-small"` to give each
seed its own Hugging Face machine.

**CV / competition** (see `examples/cv_mnist.py`):
`kaggle_runtime_start(competition="<slug>")` (data appears under `/kaggle/input/`), or
on another runtime `cv_load_dataset("<slug>", kind="competition")` → `launch_training(...)` → poll →
`cv_training_curves(run)` → `cv_show_predictions(code)` → `kaggle_submit(...)` →
`kaggle_submissions(...)`.

## Editing this server
Tools are grouped in `src/gpu_bridge/tools/`: `core`, `sessions` (start/pair/stop Colab
and Kaggle), `notebook`, `rl`, `cv`, `kaggle_tools`, `hf_jobs` (jobs + interactive
runtime), `hf_hub` (Hub + Spaces), `guide_tools`; each has `register(mcp)`, wired in
`server.py`. Connections live in `connectors/` (`jupyter.py`, `kaggle_api.py`, `hf.py`,
`pairing.py`, `store.py`); the shared singletons are in `runtime_state.py`.

`remote/entrypoint.py` is the one program that runs on every remote machine (pushed to
Kaggle, pasted into Colab, shipped to a Hugging Face job). It starts Jupyter, opens a
tunnel and announces its address where needed, and exits when idle or told to stop. It
must stay standard-library only.

The `gpu-bridge` command is `cli.py`: no arguments serves MCP over stdio; `install` /
`uninstall` / `clients` (`installer.py`) register it with AI clients; `login` hands over
to the Kaggle / Hugging Face login tools; `doctor` reports what is set up. `install.sh`
and `install.ps1` are the one-line installers. The repository address and branch they and
the Colab line use are in `config.py` (`REPO_SLUG`, `REPO_BRANCH`) and at the top of both
install scripts: update all three when the project moves.

Before committing: `uv run pytest` (real Jupyter server; spec-checked Kaggle and Hugging Face mocks)
and `uvx ruff check src tests`. After changing tool code the user must restart the MCP
(relaunch Claude Code or `/mcp` reconnect).

## Never
- Never commit secrets. Logins belong to the Kaggle and Hugging Face tools; `.mcp.json`,
  `.gpu-bridge/`, `kaggle.json` and `.env` are git-ignored.
- Never ask the user to paste a token into the chat; point them at `gpu-bridge login`.
- Never leave a Hugging Face machine running without telling the user.
- Never assume a runtime is alive after a long gap — reconnect and check.
