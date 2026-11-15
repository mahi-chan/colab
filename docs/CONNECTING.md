# Connecting both ends

thesis-mcp sits between two things, and each needs connecting once:

```
  AI client  ───────────►  thesis-mcp  ───────────►  a machine with a GPU
  (Claude, Cursor, ...)    (on your computer)        (Hugging Face, Colab, Kaggle)

  connected by the installer                         connected by the steps below
```

- **The AI client end** is done by the installer (`./install.sh` or `.\install.ps1`).
- **The machine end** is what this page covers. Pick the platform you use; you only need one.

At any time, this shows what is ready and what is missing:

```bash
uv run thesis-mcp doctor            # add --online to also verify the Hugging Face login
```

You can also just ask the assistant *"how do I connect Colab?"* (or Kaggle, or Hugging
Face). It has a `setup_guide` tool that returns these same steps, including the notebook
cell to paste.

---

## Hugging Face (rented GPU)

One-time setup, about two minutes. Nothing to paste into a notebook.

1. **Create a token.** Go to <https://huggingface.co/settings/tokens>, create a token
   with **Write** access, and copy it.
2. **Save it on your computer.** In a terminal, in the thesis-mcp folder:
   ```bash
   uv run hf auth login
   ```
   Paste the token when asked. (Alternative: set the `HF_TOKEN` environment variable for
   your AI client.)
3. **Enable billing.** Renting machines needs credits or a payment method:
   <https://huggingface.co/settings/billing>.
4. **Check it.** `uv run thesis-mcp doctor --online` should say
   `Hugging Face: logged in as <you>, can pay for machines`.

Then ask the assistant, for example:

| You say | It uses |
|---------|---------|
| "Check my Hugging Face login and show GPU prices" | `hf_whoami`, `hf_hardware` |
| "Fine-tune the LLM example on a T4 for at most 1 hour" | `hf_job_launch` |
| "Start an A10G machine so we can experiment" | `hf_runtime_start`, `hf_runtime_connect` |
| "Stop everything that is billing" | `hf_runtime_stop`, `hf_job_list` |

**Cost:** machines bill per minute until they end. Every one gets a time limit, and the
interactive machine shuts down after 30 idle minutes.

---

## Google Colab (free GPU)

Repeat these each time you start a Colab session.

1. Open <https://colab.research.google.com> and create a notebook.
2. Choose **Runtime → Change runtime type → GPU**.
3. Paste the contents of [`runtime/colab_bootstrap.py`](../runtime/colab_bootstrap.py)
   into a cell and run it. **Leave the cell running**: it hosts the connection.
4. After a few seconds it prints two lines:
   ```
   export JUPYTER_URL="https://something.trycloudflare.com"
   export JUPYTER_TOKEN="0123abcd..."
   ```
5. Give both values to the assistant: *"Connect to the runtime at `<URL>` with token
   `<TOKEN>`."* It calls `connect_runtime` and confirms the GPU.

Good to know:

- The address changes every time the cell runs again. After Colab disconnects, repeat
  steps 3–5.
- Colab deletes the machine's files when the session ends. Ask the assistant to
  *"save the checkpoints"* as you go.
- For Kaggle competitions or the Hugging Face Hub **from Colab**, fill in the optional
  credential lines at the top of the cell before running it.
- In Claude Code you can instead run the two `export` lines in your terminal before
  starting `claude`, then say *"connect the runtime"*.

---

## Kaggle (free GPU, competitions)

1. Open <https://www.kaggle.com/code> and create a notebook.
2. In the notebook settings set **Accelerator = GPU** and **Internet = On**. Both need a
   phone-verified Kaggle account.
3. Paste the contents of [`runtime/kaggle_bootstrap.py`](../runtime/kaggle_bootstrap.py)
   into a cell and run it. Leave it running.
4. Give the printed `JUPYTER_URL` and `JUPYTER_TOKEN` to the assistant, as for Colab.

Competition tools (`kaggle_submit`, `kaggle_leaderboard`, `cv_load_dataset`, ...) work
here without extra credentials, because the code runs inside Kaggle.

---

## A Hugging Face Space you already rent

For a GPU Space that runs JupyterLab (for example one made from the "JupyterLab" Docker
template):

1. Do steps 1–2 of the Hugging Face section above (token and login).
2. In the Space's settings, make sure a `JUPYTER_TOKEN` secret is set.
3. Tell the assistant: *"Connect to my Space at `https://<user>-<space-name>.hf.space`
   with Jupyter token `<TOKEN>`, using Hugging Face auth."* It calls
   `connect_runtime(url, token, hf_auth=True)`.

A Space on paid hardware bills while it runs. *"Pause my Space"* stops it.

---

## The AI client end

`./install.sh` (macOS, Linux) or `.\install.ps1` (Windows) registers the server with every
supported client it finds. To manage it by hand:

```bash
uv run thesis-mcp clients                    # which clients are found / installed
uv run thesis-mcp install --client cursor    # one client (repeatable)
uv run thesis-mcp uninstall                  # remove from all
uv run thesis-mcp install --print            # the entry to paste into any other client
```

| Client | `--client` name | After installing |
|--------|-----------------|------------------|
| Claude Code | `claude-code` | Start a new session |
| Claude Desktop | `claude-desktop` | Quit and reopen the app |
| Cursor | `cursor` | Restart; enable `thesis` under Settings → MCP |
| VS Code (GitHub Copilot) | `vscode` | Reload the window; use agent mode |
| Windsurf | `windsurf` | Restart, or refresh the MCP panel |
| Cline | `cline` | Reload VS Code |
| Gemini CLI | `gemini` | Start a new session |
| Codex CLI | `codex` | Start a new session |

**Any other client** that runs local MCP servers: paste the output of
`uv run thesis-mcp install --print` into its MCP settings.

**Clients that connect by URL** instead of starting a program: run
`uv run thesis-mcp serve --http` and point the client at `http://127.0.0.1:8765/mcp`.
This listens on your own computer only. Do not expose it to the internet: it has no
password, and whoever reaches it can rent machines on your Hugging Face account. For the
same reason, chat apps that run only in a browser and need a public server address are
not supported.

The installer never writes a token or password into any client's config.
