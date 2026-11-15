# Connecting both ends

gpu-bridge sits between two things:

```
  AI client  ───────────►  gpu-bridge  ───────────►  a machine with a GPU
  (Claude, Cursor, ...)    (on your computer)        (Kaggle, Colab, Hugging Face)

  done by the installer                              this page
```

The installer connects the AI client. This page covers the other end. You need only one
platform, and for each the manual part is a single one-time step.

`gpu-bridge doctor` shows what is ready at any time (`--online` also checks your Hugging
Face login against the network). You can also ask the assistant *"how do I connect
Kaggle?"* — it has the same steps.

---

## Kaggle — free GPU, fully automatic

**Once:**

1. Verify your phone number at <https://www.kaggle.com/settings>. Kaggle requires it
   before a session may use a GPU or the internet.
2. Log in on your computer:
   ```bash
   gpu-bridge login kaggle
   ```
   (Alternative: on the same settings page create an API token and save the downloaded
   `kaggle.json` as `~/.kaggle/kaggle.json`.)

**Every time:** just ask.

| You say | What the assistant does |
|---|---|
| "Connect a Kaggle GPU." | Starts a session on Kaggle and attaches to it (one to three minutes). |
| "Use the Titanic competition data." | Starts the session with that data under `/kaggle/input/`. |
| "Submit `submission.csv` to Titanic." | Fetches the file from the session and submits it. |
| "Stop the Kaggle session." | Ends it, so it stops using your weekly GPU hours. |

You never open the browser. The session also ends by itself after 30 idle minutes or at
its time limit (6 hours unless you ask otherwise). Files left in `/kaggle/working` are
kept on Kaggle as the output of a private notebook named *GPU Bridge Runtime*.

For a competition, accept its rules on the competition page first; Kaggle refuses to
attach the data otherwise.

---

## Google Colab — free GPU, one pasted line

Google offers no way for a program to start a Colab session, so one small step is yours.

1. Say *"connect Colab"*. The assistant replies with one line of code.
2. Open <https://colab.new>, choose **Runtime → Change runtime type → T4 GPU**, paste the
   line into the first cell and run it.
3. The cell prints `connected` and keeps running (that is expected). Tell the assistant
   it is running.

That is all: you do not copy anything back. The session finds its own way to your
computer.

Good to know:

- Each session gets a fresh line. After Colab disconnects, ask again.
- Colab deletes the machine's files when the session ends. Ask the assistant to *"save
  the checkpoints"* as you go.
- The same line also works in a Kaggle notebook (with Internet switched on), if you
  prefer not to log in to Kaggle on your computer.

---

## Hugging Face — rented GPU, fully automatic

**Once:**

1. Create a token with **Write** access at <https://huggingface.co/settings/tokens>.
2. Log in on your computer:
   ```bash
   gpu-bridge login huggingface
   ```
3. Add credits or a payment method at <https://huggingface.co/settings/billing>.

**Every time:** just ask.

| You say | What the assistant does |
|---|---|
| "Show me the GPU prices." | Lists machine types with specs and price per hour. |
| "Fine-tune the LLM example on a T4 for at most an hour." | Rents one machine for that training; it stops when the script ends. |
| "Start an A10G machine so we can experiment." | Rents an interactive machine and attaches to it. |
| "Stop everything that is billing." | Stops the machine and lists anything still running. |

Machines bill per minute until they end. Every one gets a time limit, and the
interactive machine shuts down after 30 idle minutes, first copying its runs to a private
repo on your account.

### A Space you already rent

For a GPU Space running JupyterLab, tell the assistant its address
(`https://<user>-<space-name>.hf.space`) and its `JUPYTER_TOKEN` secret and ask it to
connect with Hugging Face auth. *"Pause my Space"* stops its billing.

---

## How a new session finds your computer

A Kaggle or Colab machine cannot be reached from outside, so the program gpu-bridge
starts there opens a temporary tunnel and announces the tunnel's address:

- gpu-bridge makes a random one-time code and gives it to the session (inside the script
  it pushes to Kaggle, or in the line you paste into Colab).
- The session uses the code as its password and posts its address, signed with the code,
  to a relay ([ntfy.sh](https://ntfy.sh) by default) under a name derived from the code.
  On Kaggle the address is also read back through Kaggle's own API.
- Your computer accepts only an address with a valid signature.

The relay sees a tunnel address and nothing else. To use your own
[ntfy](https://docs.ntfy.sh/install/) server, set `GPU_BRIDGE_RENDEZVOUS_URL` for the AI
client.

---

## The AI client end

The one-line installer registers the server with every supported client it finds. To
manage it by hand:

```bash
gpu-bridge clients                    # which clients are found / installed
gpu-bridge install --client cursor    # one client (repeatable)
gpu-bridge uninstall                  # remove from all
gpu-bridge install --print            # the entry to paste into any other client
```

| Client | `--client` name | After installing |
|--------|-----------------|------------------|
| Claude Code | `claude-code` | Start a new session |
| Claude Desktop | `claude-desktop` | Quit and reopen the app |
| Cursor | `cursor` | Restart; enable `gpu-bridge` under Settings → MCP |
| VS Code (GitHub Copilot) | `vscode` | Reload the window; use agent mode |
| Windsurf | `windsurf` | Restart, or refresh the MCP panel |
| Cline | `cline` | Reload VS Code |
| Gemini CLI | `gemini` | Start a new session |
| Codex CLI | `codex` | Start a new session |

**Clients that connect by URL** instead of starting a program: run
`gpu-bridge serve --http` and point the client at `http://127.0.0.1:8765/mcp`. This
listens on your own computer only. Do not expose it to the internet: it has no password,
and whoever reaches it can rent machines on your Hugging Face account. For the same
reason, chat apps that run only in a browser and need a public server address are not
supported.

The installer never writes a token or password into any client's config.
