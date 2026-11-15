"""Step-by-step instructions for connecting each place the work can run.

Shared by the ``setup_guide`` tool (so any AI client can walk the user through it) and
the ``gpu-bridge doctor`` command — one source for the instructions.
"""

from pathlib import Path
from typing import List

PLATFORMS = ("colab", "kaggle", "huggingface", "space")


def _asset_dir(kind: str) -> Path:
    """``examples``: inside the package when installed from a wheel, otherwise at the top
    of the repository checkout."""
    packaged = Path(__file__).parent / "_assets" / kind
    return packaged if packaged.is_dir() else Path(__file__).resolve().parents[2] / kind


def list_assets(kind: str) -> List[str]:
    folder = _asset_dir(kind)
    return sorted(p.name for p in folder.glob("*.py")) if folder.is_dir() else []


def read_asset(kind: str, name: str) -> str:
    if name not in list_assets(kind):
        raise FileNotFoundError(f"No {kind} file named {name!r}. Available: {list_assets(kind)}")
    return (_asset_dir(kind) / name).read_text(encoding="utf-8")


def hf_login_command() -> str:
    from .installer import cli_command

    return f"{cli_command()} login huggingface"


def kaggle_login_command() -> str:
    from .installer import cli_command

    return f"{cli_command()} login kaggle"


def guide(platform: str) -> str:
    platform = platform.strip().lower()
    if platform == "colab":
        return """\
Connect Google Colab (free GPU). Google does not let a program start a Colab session,
so the user runs one line there; nothing is copied back.

1. Call colab_runtime_start. It returns the steps and one line of code.
2. The user opens https://colab.new, picks Runtime > Change runtime type > T4 GPU,
   pastes the line into a cell and runs it. The cell keeps running: that is expected.
3. When the cell prints "connected", call connect_runtime (no arguments). The session
   is found automatically. runtime_status then confirms the GPU.

After Colab disconnects, repeat from step 1 (each session gets a fresh line). Files on
the machine are lost when Colab recycles it: use save_checkpoint or hf_push_run as you
go. runtime_stop ends the session from here."""
    if platform == "kaggle":
        return f"""\
Connect Kaggle (free GPU, about 30 hours a week). Fully automatic after a one-time login.

One-time setup, done by the user:
1. On https://www.kaggle.com/settings verify the phone number (Kaggle requires it for
   GPU and internet access).
2. Log in on this computer, in a terminal:
       {kaggle_login_command()}
   (Alternative: create an API token on the same settings page and save the downloaded
   kaggle.json as ~/.kaggle/kaggle.json.)

Every session, done by the assistant:
   kaggle_runtime_start()           start a GPU session; no browser needed
   connect_runtime()                attach (repeat until it is up, one to three minutes)
   runtime_stop()                   end it and stop using GPU hours

For a competition: kaggle_runtime_start(competition="<slug>") attaches its data under
/kaggle/input/ (the user must have accepted the rules on the competition page). The
kaggle_* tools (files, submit, submissions, leaderboard) work with the same login.

Without the login, a Kaggle notebook can still be connected like Colab: call
colab_runtime_start and have the user run its line in a Kaggle notebook with
Internet switched on."""
    if platform == "huggingface":
        return f"""\
Connect Hugging Face (rented CPU/GPU machines, billed per minute). One-time setup:

1. Create a token with WRITE access at https://huggingface.co/settings/tokens
2. Save it on this computer by running once, in a terminal:
       {hf_login_command()}
   (Alternative: set the HF_TOKEN environment variable for the AI client.)
3. Renting needs credits or a payment method: https://huggingface.co/settings/billing

Then the assistant can:
   hf_whoami                      check the login and whether the account can pay
   hf_hardware                    list machine types and prices
   hf_job_launch(script, run_name, flavor, timeout)
                                  one machine for one training; stops by itself
   hf_runtime_start(flavor, timeout) then hf_runtime_connect
                                  an interactive machine, used like Colab
   hf_runtime_stop / hf_job_list  stop billing / see what is still running

Always agree the machine type and time limit with the user before renting a GPU."""
    if platform == "space":
        return """\
Connect a Hugging Face Space that runs JupyterLab (a GPU Space the user already rents).

1. The Space must run Jupyter, e.g. one created from the "JupyterLab" Docker template,
   with a JUPYTER_TOKEN secret set in its settings.
2. Its address is https://<user>-<space-name>.hf.space (hf_space_status shows it).
3. The Hugging Face login must be set up first: setup_guide("huggingface"), steps 1-2.
4. The assistant calls
       connect_runtime(url="https://<user>-<space-name>.hf.space",
                       token="<the JUPYTER_TOKEN secret>", hf_auth=True)

A Space on paid hardware bills while it runs: hf_space_pause stops it, hf_space_restart
resumes it, hf_space_hardware changes the machine type or sets an idle sleep time."""
    return f"Unknown platform {platform!r}. Choose one of: {', '.join(PLATFORMS)}."
