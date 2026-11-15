"""``thesis-mcp doctor``: what is set up, and what still needs doing."""

import sys

from . import __version__, config, guide, installer


def endpoints(online: bool = False) -> str:
    """Readiness of each place the work can run, with the next step for each."""
    from . import runtime_state as rs
    from .connectors import hf

    lines = []
    try:
        hf.token()
        status = "token found"
        if online:
            try:
                me = hf.api().whoami(token=hf.token())
                pay = {True: "can pay for machines", False: "NO payment method or credits"}.get(
                    me.get("canPay"), "billing status unknown")
                status = f"logged in as {me.get('name')}, {pay}"
            except Exception as exc:  # noqa: BLE001 - report any failure, never crash the report
                status = f"token found, but the check failed: {exc}"
        lines.append(f"[ready]   Hugging Face: {status}.")
    except hf.HfNotLoggedIn:
        lines.append("[to do]   Hugging Face: no token. Run once:  " + guide.hf_login_command()
                     + "\n          (token with write access from https://huggingface.co/settings/tokens)")

    saved = rs.store.get_kernel()
    if config.JUPYTER_URL:
        lines.append(f"[ready]   Colab/Kaggle: JUPYTER_URL is set ({config.JUPYTER_URL}); "
                     "ask the assistant to connect.")
    elif saved.get("url"):
        lines.append(f"[known]   Last runtime: {saved['url']}. Ask the assistant to reconnect "
                     "(it may have shut down since).")
    else:
        lines.append("[to do]   Colab/Kaggle: nothing connected. Run the bootstrap cell in a notebook "
                     "and give the printed URL and token to the assistant.")

    job = rs.store.get_section("hf_runtime").get("job_id")
    if job:
        lines.append(f"[billing] A Hugging Face runtime was started (job {job}). "
                     "Ask the assistant to connect to it or stop it.")
    lines.append("[info]    Kaggle competitions: credentials live on the machine that runs the code "
                 "(automatic on Kaggle; see the top of the Colab cell otherwise).")
    return "\n".join(lines)


def report(online: bool = False) -> str:
    from . import runtime_state as rs

    out = [f"thesis-mcp {__version__}  (Python {sys.version.split()[0]})",
           "Server command: " + " ".join(installer.server_command()),
           "", "AI clients"]
    for client in installer.CLIENTS.values():
        if installer.is_installed(client):
            out.append(f"  [installed] {client.label}")
        elif client.detected():
            out.append(f"  [found]     {client.label}; add it with:  "
                       f"{installer.cli_command()} install --client {client.key}")
    if len(out) == 4:
        out.append(f"  none found. Run:  {installer.cli_command()} install --client <name>")
    out += ["", "Where the work runs", endpoints(online), "",
            f"State: {config.STATE_DIR}  ({len(rs.store.list_runs())} runs recorded)",
            "Full steps for any platform: ask the assistant, or see docs/CONNECTING.md"]
    return "\n".join(out)
