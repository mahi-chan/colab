<h1 align="center">thesis-mcp</h1>

<p align="center">
  <b>Run your machine-learning work on free and rented GPUs, straight from your AI assistant.</b><br>
  Kaggle · Google Colab · Hugging Face — one MCP server, one workflow.
</p>

<p align="center">
  <a href="https://github.com/mahi-chan/colab/actions/workflows/tests.yml"><img alt="tests" src="https://github.com/mahi-chan/colab/actions/workflows/tests.yml/badge.svg?branch=claude%2Fmcp-colab-kaggle-3nheg4"></a>
  <img alt="python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <img alt="platforms" src="https://img.shields.io/badge/installs%20on-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey">
  <img alt="license MIT" src="https://img.shields.io/badge/license-MIT-green">
</p>

---

You say *"fine-tune this model on a T4"* or *"train PPO on CartPole with three seeds and
show me the reward curves"*. Your assistant gets a GPU, runs the training in the
background, follows it, shows you the plots, and saves the results before the machine
disappears. thesis-mcp is the piece in between: a
[Model Context Protocol](https://modelcontextprotocol.io) server that runs on your
computer and gives any MCP-capable assistant the tools to do that.

```
 Your AI assistant ─────►  thesis-mcp  ─────►  Kaggle GPU      free, started for you
 (Claude, Cursor,          on your             Colab GPU       free, one pasted line
  Copilot, Gemini…)        computer            Hugging Face    rented, per minute
```

## Install

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/mahi-chan/colab/claude/mcp-colab-kaggle-3nheg4/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/mahi-chan/colab/claude/mcp-colab-kaggle-3nheg4/install.ps1 | iex
```

That one line downloads thesis-mcp, sets up its own Python environment (it installs
[uv](https://docs.astral.sh/uv/) if you don't have it), registers the server with every
supported AI client it finds, and adds a `thesis-mcp` command. Nothing else is needed —
not even git or Python. Run the same line again to update.

Then **restart your AI client** and say:

> connect a Kaggle GPU

### Supported AI clients

Claude Code · Claude Desktop · Cursor · VS Code (GitHub Copilot) · Windsurf · Cline ·
Gemini CLI · Codex CLI

Any other client that can start a local MCP server works too: `thesis-mcp install --print`
gives you the entry to paste into its settings.

## Where your work runs

You need **one** of these. Each takes a single one-time step, and after that the
assistant does the rest.

| | Cost | One-time setup | Starting a session |
|---|---|---|---|
| **Kaggle** | Free, about 30 GPU-hours a week | `thesis-mcp login kaggle` | Automatic. No browser. |
| **Google Colab** | Free | None | You run one pasted line in a Colab cell. Nothing to copy back. |
| **Hugging Face** | Paid per minute | `thesis-mcp login huggingface` | Automatic. |

Not sure where you stand? `thesis-mcp doctor` shows what is ready and what is missing.
Or ask the assistant *"how do I connect Kaggle?"* — it knows the steps.
The full walkthrough is in [docs/CONNECTING.md](docs/CONNECTING.md).

<details>
<summary><b>Why does Colab need a pasted line when Kaggle doesn't?</b></summary>

Kaggle has an official API for starting a session; Colab does not, so a program cannot
start one for you. thesis-mcp keeps it to the minimum: the assistant gives you one line,
you run it in a new notebook, and the session connects by itself.
</details>

## What you can ask

| You say | What happens |
|---|---|
| "Connect a Kaggle GPU." | Starts a GPU session on Kaggle and attaches to it. |
| "Join the Titanic competition, train a baseline and submit it." | Attaches the data, trains in the background, submits, shows your score. |
| "Train PPO on CartPole with seeds 0, 1 and 2 and plot the rewards." | Three background runs, then reward curves in the chat. |
| "Fine-tune SmolLM2 with LoRA on a T4 for at most an hour." | Rents one Hugging Face machine for that job; it stops when training ends. |
| "How is the run going?" | Status, latest metrics, the log tail. |
| "Save the checkpoints." | Downloads them, or pushes them to a private Hugging Face repo. |
| "Stop everything." | Ends the session and anything still billing. |

## Why not just a notebook?

- **Training that survives.** Long runs go to the background on the remote machine, so
  they never hit a chat timeout and keep going if your connection drops. A new chat
  re-attaches to them.
- **One workflow everywhere.** The same training script and the same follow-up (status,
  logs, metrics, plots, stop) work on Kaggle, Colab and Hugging Face.
- **Results that outlive the machine.** Remote disks are temporary. Checkpoints download
  to your computer or go straight to a private Hugging Face repo.
- **Guards on rented GPUs.** Every Hugging Face machine gets a time limit, the
  interactive one shuts itself down when idle, and one tool lists what is still billing.
- **Built for experiments.** Multi-seed sweeps, metric curves, RL rollouts, prediction
  visualisations and Kaggle submissions are single requests.

## Tools

<details>
<summary>All 54 tools, by group</summary>

| Group | Tools |
|---|---|
| Get a machine | `kaggle_runtime_start`, `colab_runtime_start`, `connect_runtime`, `runtime_stop`, `runtime_status` |
| Hugging Face machines | `hf_hardware`, `hf_job_launch`, `hf_job_list`, `hf_job_cancel`, `hf_runtime_start`, `hf_runtime_connect`, `hf_runtime_stop` |
| Run code and files | `run_code`, `upload_file`, `download_file`, `fetch_image` |
| Training runs | `launch_training`, `get_run_status`, `get_logs`, `get_metrics`, `plot_metrics`, `stop_run`, `list_runs`, `save_checkpoint`, `restore_checkpoint` |
| Notebooks | `notebook_create`, `notebook_read`, `notebook_add_cell`, `notebook_edit_cell`, `notebook_delete_cell`, `notebook_run_cell` |
| Reinforcement learning | `rl_setup`, `rl_reward_curve`, `rl_record_rollout`, `rl_seed_sweep` |
| Computer vision | `cv_load_dataset`, `cv_training_curves`, `cv_show_predictions` |
| Kaggle competitions | `kaggle_search_datasets`, `kaggle_competition_files`, `kaggle_submit`, `kaggle_submissions`, `kaggle_leaderboard` |
| Hugging Face Hub and Spaces | `hf_whoami`, `hf_search`, `hf_upload`, `hf_download`, `hf_push_run`, `hf_space_status`, `hf_space_hardware`, `hf_space_pause`, `hf_space_restart` |
| Help | `setup_guide`, `example_script` |

</details>

### Training scripts

Any Python script works. Four names are provided for you (don't import them):

| Name | Purpose |
|---|---|
| `log_metric(step, **values)` | Record numbers; they feed the status, metrics and plot tools. |
| `save_checkpoint_file(path)` | Keep a file or folder as a checkpoint. |
| `THESIS_RUN_DIR` | This run's working folder. |
| `SEED` | This run's seed (set by a sweep). |

Ready-made examples: [LoRA fine-tune of a language model](examples/llm_lora_finetune.py),
[PPO on CartPole](examples/rl_cartpole.py), [CNN on MNIST](examples/cv_mnist.py).

## The `thesis-mcp` command

```
thesis-mcp doctor               what is set up, and the next step for anything missing
thesis-mcp login kaggle         log in to Kaggle (once)
thesis-mcp login huggingface    log in to Hugging Face (once)
thesis-mcp clients              which AI clients were found and where it is installed
thesis-mcp install              register with AI clients (--client NAME, --print)
thesis-mcp uninstall            remove it from them
thesis-mcp serve --http         serve over local HTTP for clients that connect by URL
```

## Costs

- **Kaggle and Colab are free.** Kaggle sessions started here end on request, after 30
  idle minutes, or at the time limit, so they don't burn your weekly GPU hours.
- **Hugging Face bills per minute** until a machine ends. The assistant is told to agree
  the machine type and a time limit with you first. `hf_hardware` shows current prices.

## Security and privacy

- Your logins stay with the official Kaggle and Hugging Face tools on your computer.
  thesis-mcp never writes a token into an AI client's config or into this repository.
- A Kaggle or Colab session is reached through a temporary public tunnel, protected by a
  random one-time code that only your computer and that session know.
- To find a new session without you copying anything, the session posts its tunnel
  address to a relay ([ntfy.sh](https://ntfy.sh) by default). Only that address passes
  through, signed so it cannot be swapped, and the code never leaves your machines.
  Set `THESIS_RENDEZVOUS_URL` to use your own relay.
- When a tool needs your Hugging Face or Kaggle login on the remote machine (pushing
  checkpoints, downloading competition data), it is lent for that one command and not
  stored there.
- `thesis-mcp serve --http` listens on your computer only. Do not expose it to the
  internet: it has no password.

## Troubleshooting

| Symptom | What to do |
|---|---|
| The assistant has no thesis tools | Restart the AI client. Check `thesis-mcp clients`. |
| "No Kaggle login found" | `thesis-mcp login kaggle` |
| A Kaggle session "ended before connecting" | Verify your phone number on kaggle.com (needed for GPU and internet), or the weekly GPU quota is used up. |
| "Not connected yet" on Colab | Make sure the pasted line is still running and has printed `connected`. |
| "No Hugging Face token found" | `thesis-mcp login huggingface` |
| Hugging Face error 402 | Add credits or a payment method at huggingface.co/settings/billing. |
| A run disappeared | The machine was recycled. Save checkpoints as you go. |

## Status

Tested automatically on Linux, macOS and Windows: the installers, every tool against a
real Jupyter server, and every Kaggle and Hugging Face call against the real libraries'
interfaces. The Hugging Face machine image, the LoRA example and the PPO example have been
run for real on CPU. Sessions on the live Kaggle, Colab and Hugging Face services depend
on your accounts and are not part of the automated tests — if something misbehaves there,
please open an issue with the message you saw.

## Development

```bash
git clone -b claude/mcp-colab-kaggle-3nheg4 https://github.com/mahi-chan/colab.git thesis-mcp
cd thesis-mcp
uv sync
uv run pytest              # about a minute
uvx ruff check src tests
./install.sh               # register this checkout with your AI clients
```

```
src/thesis_mcp/
  cli.py, installer.py     the thesis-mcp command and the client installer
  server.py                registers every tool group
  tools/                   the tools, one module per group
  connectors/              Jupyter, Kaggle, Hugging Face, pairing, local state
  remote/entrypoint.py     the program that runs on the remote machine
examples/                  training scripts
docs/CONNECTING.md         connecting each platform, step by step
tests/                     test suite
```

[`CLAUDE.md`](CLAUDE.md) holds the working notes an assistant reads when developing in
this repository.

## License

MIT
