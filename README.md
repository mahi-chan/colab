# thesis-mcp

An MCP server that lets **Claude Code drive a Google Colab or Kaggle GPU** for ML
thesis work — reinforcement learning **or** computer vision. It gives the agent
higher-level tools than raw cell execution: connect to a cloud runtime, edit/run
notebook cells, launch long training jobs that survive disconnects, track metrics,
render plots and rollouts back into chat, and submit to Kaggle competitions.

```
Claude Code  ──stdio──►  thesis-mcp (this repo, runs on YOUR machine)
                              │  requests + websocket
                              ▼
                     Jupyter Server in a Colab/Kaggle VM  ──►  GPU, your data
                     (started by runtime/colab_bootstrap.py, exposed via cloudflared)
```

The server is tiny locally (only `mcp`, `requests`, `websocket-client`) — all the
heavy ML libraries live on the cloud runtime.

## Why not just the official Colab/Kaggle MCPs?
Google's `googlecolab/colab-mcp` and Kaggle's MCP give you low-level cell/API access.
This adds the thesis workflow on top: **fire-and-poll training** (so hours-long runs
don't hit tool timeouts), **checkpoint-to-local** (so a dropped VM doesn't lose your
results), metric plotting, RL rollout video, multi-seed sweeps, and the CV→Kaggle
submission loop.

---

## Setup (once)

**Prerequisites:** [uv](https://docs.astral.sh/uv/) and Claude Code on your local
machine; a Google/Kaggle account for the GPU.

```bash
git clone <this-repo> && cd colab
uv sync                     # create the local venv + install deps
uv run pytest               # optional: offline smoke tests
```

**Register the MCP with Claude Code.** Because `.mcp.json` defines an executable
server, it isn't committed — activate it one of two ways:

```bash
# A) copy the template (it reads JUPYTER_URL/JUPYTER_TOKEN from your shell at launch)
cp .mcp.json.example .mcp.json

# B) or add it via the CLI (local scope, not committed)
claude mcp add thesis -- uv run thesis-mcp
```

## Every session

1. **Start a runtime.** Open [Google Colab](https://colab.research.google.com),
   set **Runtime → Change runtime type → GPU**, paste the contents of
   `runtime/colab_bootstrap.py` into a cell, and run it. Leave it running.
   *(Kaggle: use `runtime/kaggle_bootstrap.py`, enable GPU + Internet.)*

2. **Export the printed connection info**, then launch Claude Code from this repo:
   ```bash
   export JUPYTER_URL="https://xxxx.trycloudflare.com"
   export JUPYTER_TOKEN="....."
   claude          # start Claude Code in this directory
   ```

3. **In Claude Code:** ask it to `connect_runtime`, then work. Example prompts:
   - *"Connect the runtime and show me the GPU."*
   - *"Launch the CartPole PPO example for 50k steps, then plot the reward curve."*
   - *"Download the `<competition>` data, train the MNIST example, and submit."*

Because you `/clear` between sessions, the repo carries the memory:
[`CLAUDE.md`](./CLAUDE.md) re-teaches the workflow, and the server re-attaches to the
still-running kernel — your launched runs keep going.

---

## Tool reference

| Group | Tools |
|-------|-------|
| Runtime / exec | `connect_runtime`, `runtime_status`, `run_code`, `upload_file`, `download_file`, `fetch_image` |
| Training (fire-and-poll) | `launch_training`, `get_run_status`, `get_logs`, `get_metrics`, `stop_run`, `list_runs`, `plot_metrics`, `save_checkpoint`, `restore_checkpoint` |
| Notebook cells | `notebook_create`, `notebook_read`, `notebook_add_cell`, `notebook_edit_cell`, `notebook_delete_cell`, `notebook_run_cell` |
| Reinforcement learning | `rl_setup`, `rl_reward_curve`, `rl_record_rollout`, `rl_seed_sweep` |
| Computer vision | `cv_load_dataset`, `cv_training_curves`, `cv_show_predictions` |
| Kaggle | `kaggle_search_datasets`, `kaggle_competition_files`, `kaggle_submit`, `kaggle_submissions`, `kaggle_leaderboard` |

Training scripts get these injected (don't import them): `log_metric(step, **kv)`,
`save_checkpoint_file(path)`, `THESIS_RUN_DIR`, `SEED`. See `examples/`.

### RL quickstart
```
rl_setup("classic-control")
launch_training(open("examples/rl_cartpole.py").read(), "ppo_cartpole",
                requirements="gymnasium[classic-control] stable-baselines3")
# ...poll get_run_status("ppo_cartpole")...
rl_reward_curve("ppo_cartpole")
```

### CV quickstart
```
launch_training(open("examples/cv_mnist.py").read(), "mnist_cnn",
                requirements="torch torchvision")
cv_training_curves("mnist_cnn")
```

---

## Configuration (environment variables)

| Var | Purpose |
|-----|---------|
| `JUPYTER_URL` | Public URL of the runtime's Jupyter server (from the bootstrap cell). |
| `JUPYTER_TOKEN` | Auth token for it (from the bootstrap cell). |
| `THESIS_CONTENTS_ROOT` | Override the runtime file root (auto-detected: `/content` on Colab, `/kaggle/working` on Kaggle). |
| `THESIS_RUN_ROOT` | Override where runs are stored on the runtime. |
| `THESIS_STATE_DIR` | Local dir for the run registry + saved checkpoints (default `~/.thesis-mcp`). |

For Kaggle dataset/competition tools, set `KAGGLE_USERNAME` / `KAGGLE_KEY` **inside the
Colab bootstrap cell** (they run on the runtime). On Kaggle notebooks it's automatic.

## Troubleshooting
- **`connect_runtime` fails / times out** — the bootstrap cell stopped. Re-run it and
  re-export the new `JUPYTER_URL`/`JUPYTER_TOKEN` (the tunnel URL changes each time).
- **No GPU** — set Colab Runtime type to GPU (or Kaggle Accelerator), then re-run bootstrap.
- **A run "disappeared"** — the VM was recycled. `save_checkpoint` early and often;
  `restore_checkpoint` onto a fresh runtime to resume.
- **Kaggle tool errors** — credentials aren't set on the runtime (see above).

## Security
The tunnel exposes a Jupyter server that can execute code on your VM; the random token
is the only guard, so don't share the URL/token. Nothing sensitive is committed —
tokens come from the environment and `.thesis-mcp/`, `kaggle.json`, `.env` are ignored.

## Layout
```
src/thesis_mcp/
  server.py            FastMCP app; registers all tool groups
  runtime_state.py     shared singletons (Jupyter client, run store, path helpers)
  config.py            env-var configuration
  connectors/          jupyter.py (kernel WS + contents API), store.py (local state)
  tools/               core, notebook, rl, cv, kaggle_tools
runtime/               colab_bootstrap.py, kaggle_bootstrap.py  (paste into a cell)
examples/              rl_cartpole.py, cv_mnist.py
tests/                 offline smoke tests
```

Licensed MIT.
