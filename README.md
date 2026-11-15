# thesis-mcp

An MCP server that lets **Claude Code run your ML work on remote GPUs**: Google Colab,
Kaggle, and rented Hugging Face machines. Train RL agents and vision models, fine-tune
LLMs, run experiments across seeds, and enter Kaggle competitions — from one chat.

```
Claude Code ──stdio──► thesis-mcp (this repo, on YOUR computer)
                           │
        ┌──────────────────┼─────────────────────────────┐
        ▼                  ▼                             ▼
  Colab / Kaggle     Hugging Face runtime          Hugging Face batch job
  (free GPU,         (rented GPU running           (one rented GPU per
   bootstrap cell)    Jupyter, pay per minute)      training, stops itself)
```

What it adds over plain notebook access:

- **Fire-and-poll training** — long runs go to the background, so they never hit a tool
  timeout and survive a dropped connection.
- **One workflow everywhere** — the same training script and the same follow-up tools
  (status, logs, metrics, plots, stop) work on Colab, Kaggle and Hugging Face.
- **Results that outlive the machine** — checkpoints download to your computer or go
  straight to a private Hugging Face Hub repo.
- **Cost guards for rented GPUs** — every Hugging Face machine gets a time limit, the
  interactive one shuts itself down when idle, and one tool lists what is still billing.

---

## Setup (once)

**You need:** [uv](https://docs.astral.sh/uv/) and Claude Code on your computer.

```bash
git clone https://github.com/mahi-chan/colab.git && cd colab
uv sync                       # installs the exact versions pinned in uv.lock
uv run pytest                 # optional self-check, about a minute
cp .mcp.json.example .mcp.json   # registers the server for Claude Code in this folder
```

Then start `claude` in this folder and approve the `thesis` server when asked.
(Alternative to the `cp`: `claude mcp add thesis -- uv run thesis-mcp`.)

### Accounts, depending on where you want to run

| Where | What to set up |
|-------|----------------|
| **Hugging Face** | A token with **write** access from <https://huggingface.co/settings/tokens>, then `uv run hf auth login` once (or `export HF_TOKEN=hf_...`). Renting machines needs credits or a payment method: <https://huggingface.co/settings/billing>. |
| **Colab** | A Google account. Nothing to install. |
| **Kaggle** | A Kaggle account. For competitions from Colab or Hugging Face, put your Kaggle API credentials on that machine (see the comment at the top of `runtime/colab_bootstrap.py`). |

---

## Using it

### A. Hugging Face (rented GPU) — nothing to paste anywhere

Just ask Claude Code. Typical requests:

- *"Check my Hugging Face login and show me the GPU prices."* → `hf_whoami`, `hf_hardware`
- *"Fine-tune the LoRA example on a T4 for at most an hour."* → `hf_job_launch`, one
  machine for that training; it stops when the script ends.
- *"Start an A10G machine so we can experiment interactively."* → `hf_runtime_start` +
  `hf_runtime_connect`; from then on it behaves like a Colab runtime.
- *"Stop everything that is billing."* → `hf_runtime_stop`, `hf_job_list`

Two ways to rent:

| | Batch job (`hf_job_launch`) | Interactive runtime (`hf_runtime_start`) |
|---|---|---|
| Best for | A long training you can describe up front (LLM fine-tunes, sweeps) | Exploring, debugging, notebooks, several short runs |
| Billing ends | When the script ends, fails or hits `timeout` | On `hf_runtime_stop`, `timeout`, or after `idle_minutes` idle |
| Checkpoints | Uploaded to the private Hub repo `<you>/<run_name>` | On the machine until you `save_checkpoint` / `hf_push_run` |

### B. Colab or Kaggle (free GPU)

1. Open [Colab](https://colab.research.google.com) and set **Runtime → Change runtime
   type → GPU** (Kaggle: Accelerator = GPU and Internet = On).
2. Paste `runtime/colab_bootstrap.py` (or `runtime/kaggle_bootstrap.py`) into a cell and
   run it. Leave it running.
3. Export the two lines it prints, then start Claude Code from this folder:
   ```bash
   export JUPYTER_URL="https://xxxx.trycloudflare.com"
   export JUPYTER_TOKEN="....."
   claude
   ```
4. Ask Claude Code to *"connect the runtime"*.

### Every session after `/clear`

The repo carries the memory: [`CLAUDE.md`](./CLAUDE.md) re-teaches the workflow, and the
server re-attaches to the machine and runs that are still going. Just say *"reconnect"*.

---

## Tools

| Group | Tools |
|-------|-------|
| Runtime | `connect_runtime`, `runtime_status`, `run_code`, `upload_file`, `download_file`, `fetch_image` |
| Runs | `launch_training`, `get_run_status`, `get_logs`, `get_metrics`, `stop_run`, `list_runs`, `plot_metrics`, `save_checkpoint`, `restore_checkpoint` |
| Notebook cells | `notebook_create`, `notebook_read`, `notebook_add_cell`, `notebook_edit_cell`, `notebook_delete_cell`, `notebook_run_cell` |
| Reinforcement learning | `rl_setup`, `rl_reward_curve`, `rl_record_rollout`, `rl_seed_sweep` |
| Computer vision | `cv_load_dataset`, `cv_training_curves`, `cv_show_predictions` |
| Kaggle competitions | `kaggle_search_datasets`, `kaggle_competition_files`, `kaggle_submit`, `kaggle_submissions`, `kaggle_leaderboard` |
| Hugging Face compute | `hf_hardware`, `hf_job_launch`, `hf_job_list`, `hf_job_cancel`, `hf_runtime_start`, `hf_runtime_connect`, `hf_runtime_stop` |
| Hugging Face Hub and Spaces | `hf_whoami`, `hf_search`, `hf_upload`, `hf_download`, `hf_push_run`, `hf_space_status`, `hf_space_hardware`, `hf_space_pause`, `hf_space_restart` |

### Writing a training script

Any Python script works. Four names are injected for you — do not import them:

| Name | Purpose |
|------|---------|
| `log_metric(step, **values)` | Record numbers; read back by `get_metrics` and the plot tools. |
| `save_checkpoint_file(path)` | Keep a file or folder as a checkpoint. |
| `THESIS_RUN_DIR` | This run's working directory. |
| `SEED` | The seed for this run (set by `rl_seed_sweep`, or `THESIS_SEED`). |

Ready-made examples: [`examples/llm_lora_finetune.py`](examples/llm_lora_finetune.py)
(LoRA fine-tune of a causal LM), [`examples/rl_cartpole.py`](examples/rl_cartpole.py)
(PPO), [`examples/cv_mnist.py`](examples/cv_mnist.py) (CNN).

---

## Configuration

All optional except the credentials for the platform you use.

| Variable | Purpose |
|----------|---------|
| `HF_TOKEN` | Hugging Face token (not needed after `hf auth login`). |
| `JUPYTER_URL`, `JUPYTER_TOKEN` | Colab/Kaggle connection, printed by the bootstrap cell. |
| `THESIS_HF_IMAGE` | Docker image for `hf_runtime_start` (default: an official PyTorch + CUDA image). |
| `THESIS_STATE_DIR` | Where the run registry and downloaded checkpoints live (default `~/.thesis-mcp`). |
| `THESIS_CONTENTS_ROOT`, `THESIS_RUN_ROOT` | Override the auto-detected folders on the runtime. |

## Troubleshooting

- **"No Hugging Face token found"** — run `uv run hf auth login`, or export `HF_TOKEN`
  and restart Claude Code.
- **Hugging Face error 402** — the account has no credits or payment method.
- **Hugging Face error 403** — the token is read-only or lacks permission for the action.
- **`hf_runtime_connect` says "not ready yet"** — normal for the first minute or two;
  call it again.
- **`connect_runtime` fails on Colab/Kaggle** — the bootstrap cell stopped. Re-run it and
  export the new URL and token (the tunnel address changes every time).
- **A run disappeared** — the machine was recycled. Save checkpoints early
  (`save_checkpoint` or `hf_push_run`).
- **Kaggle tool errors** — the machine has no Kaggle credentials (see Setup).

## Security

- No secret is ever written to the repo or to the state file. Tokens come from the
  environment or the Hugging Face login.
- On Colab/Kaggle the tunnel exposes a Jupyter server that can run code on that VM; the
  random token is the only guard, so do not share the URL or token.
- A Hugging Face runtime sits behind Hugging Face's own access control (your token) plus
  a second, per-machine Jupyter token. Your Hugging Face token is given to machines you
  rent, as an encrypted secret, so they can read gated models and upload checkpoints.

## Development

```bash
uv run pytest                 # integration tests against a real local Jupyter server,
                              # Hugging Face calls checked against the real library signatures
uvx ruff check src tests
```

```
src/thesis_mcp/
  server.py            registers every tool group
  runtime_state.py     shared connection + run registry
  connectors/          jupyter.py, hf.py, store.py
  tools/               core, notebook, rl, cv, kaggle_tools, hf_jobs, hf_hub
  remote/              hf_entrypoint.py — runs on a rented Hugging Face machine
runtime/               Colab and Kaggle bootstrap cells
examples/              training scripts
tests/                 test suite and remote-side stubs
```

Licensed MIT.
