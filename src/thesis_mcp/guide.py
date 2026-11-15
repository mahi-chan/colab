"""Step-by-step instructions for connecting each place the work can run.

Shared by the ``setup_guide`` tool (so any AI client can walk the user through it), the
``thesis-mcp doctor`` command, and nothing else — one source for the instructions.
"""

import sys
from pathlib import Path
from typing import List

PLATFORMS = ("colab", "kaggle", "huggingface", "space")


def _asset_dir(kind: str) -> Path:
    """``runtime`` or ``examples``: inside the package when installed from a wheel,
    otherwise at the top of the repository checkout."""
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
    """The `hf` program that belongs to this installation, by full path."""
    exe = Path(sys.executable).parent / ("hf.exe" if sys.platform == "win32" else "hf")
    return f'"{exe}" auth login' if exe.exists() else "hf auth login"


def _notebook_steps(site: str, settings: str, cell_file: str, extra: str) -> str:
    return f"""\
Connect {site} (free GPU). The user does steps 1-3 in their browser.

1. {settings}
2. Paste the cell below into the notebook and run it. Leave it running: it hosts the
   connection, and stopping it disconnects the assistant.
3. After a few seconds the cell prints two lines, JUPYTER_URL and JUPYTER_TOKEN.
   Give both values to the assistant.
4. The assistant calls connect_runtime(url="<JUPYTER_URL>", token="<JUPYTER_TOKEN>"),
   then runtime_status to confirm the GPU.

{extra}
The address changes every time the cell is run again, so repeat steps 2-4 after the
notebook disconnects. Runs and files on the machine are lost when it is recycled:
download results with save_checkpoint (or hf_push_run) as you go.

----- cell to paste ({cell_file}) -----
{read_asset("runtime", cell_file)}"""


def guide(platform: str) -> str:
    platform = platform.strip().lower()
    if platform == "colab":
        return _notebook_steps(
            "Google Colab",
            "Open https://colab.research.google.com, create a notebook, and choose "
            "Runtime > Change runtime type > GPU.",
            "colab_bootstrap.py",
            "For Kaggle competitions or the Hugging Face Hub from Colab, fill in the optional\n"
            "credential lines at the top of the cell before running it.\n",
        )
    if platform == "kaggle":
        return _notebook_steps(
            "Kaggle Notebooks",
            "Open https://www.kaggle.com/code, create a notebook, and in its settings set "
            "Accelerator = GPU and Internet = On (both need a phone-verified account).",
            "kaggle_bootstrap.py",
            "Kaggle competition tools work here without extra credentials.\n",
        )
    if platform == "huggingface":
        return f"""\
Connect Hugging Face (rented CPU/GPU machines, billed per minute). One-time setup:

1. Create a token with WRITE access at https://huggingface.co/settings/tokens
2. Save it on this computer by running once, in a terminal:
       {hf_login_command()}
   (Alternative: set the HF_TOKEN environment variable for the AI client.)
3. Renting needs credits or a payment method: https://huggingface.co/settings/billing

There is nothing to paste into a notebook. Then the assistant can:
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
