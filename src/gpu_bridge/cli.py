"""Command line of gpu-bridge.

With no arguments it serves MCP over stdio, which is what AI clients run. The other
commands set it up: ``install`` registers it with AI clients, ``login`` logs in to Kaggle
or Hugging Face, ``doctor`` reports what is ready and what still needs doing.
"""

import argparse
import sys
from typing import List, Optional


def _serve(args: argparse.Namespace) -> int:
    from .server import mcp

    if getattr(args, "http", False):
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        print(f"gpu-bridge serving on http://{args.host}:{args.port}/mcp", file=sys.stderr)
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
    return 0


def _install(args: argparse.Namespace) -> int:
    from . import installer

    if args.print:
        print(installer.snippet())
        return 0
    return installer.run(args.client or [], remove=args.command == "uninstall", dry_run=args.dry_run)


def _clients(_args: argparse.Namespace) -> int:
    from . import installer

    print("client          found  installed  config")
    for client in installer.CLIENTS.values():
        found = "yes" if client.detected() else "no"
        installed = "yes" if installer.is_installed(client) else "no"
        print(f"{client.key:<15} {found:<6} {installed:<10} {client.path()}")
    return 0


def _login(args: argparse.Namespace) -> int:
    """Hand over to the platform's own login program; nothing is stored by gpu-bridge."""
    import subprocess
    from pathlib import Path

    if args.platform == "kaggle":
        command = [sys.executable, "-m", "kaggle", "auth", "login"]
        print("Logging in to Kaggle. If asked, also verify your phone number at "
              "https://www.kaggle.com/settings (Kaggle requires it for GPU and internet).\n")
    else:
        hf = Path(sys.executable).parent / ("hf.exe" if sys.platform == "win32" else "hf")
        command = [str(hf), "auth", "login"]
        print("Logging in to Hugging Face. Create a token with WRITE access at "
              "https://huggingface.co/settings/tokens and paste it below.\n")
    return subprocess.call(command)


def _doctor(args: argparse.Namespace) -> int:
    from . import doctor

    print(doctor.report(online=args.online))
    return 0


def build_parser() -> argparse.ArgumentParser:
    from .installer import CLIENTS

    parser = argparse.ArgumentParser(
        prog="gpu-bridge",
        description="Run ML work on Colab, Kaggle and Hugging Face GPUs from an AI assistant. "
                    "With no command, serves MCP over stdio.")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="run the MCP server (default)")
    serve.add_argument("--http", action="store_true",
                       help="serve over HTTP instead of stdio, for clients that connect by URL")
    serve.add_argument("--host", default="127.0.0.1", help="HTTP bind address (default: this computer only)")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(run=_serve)

    for name, text in (("install", "register the server with AI clients"),
                       ("uninstall", "remove the server from AI clients")):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("--client", action="append", choices=sorted(CLIENTS), metavar="NAME",
                         help=f"one of: {', '.join(sorted(CLIENTS))}. Repeatable. "
                              "Default: every client found on this computer.")
        cmd.add_argument("--dry-run", action="store_true", help="show what would change")
        cmd.add_argument("--print", action="store_true",
                         help="print the config entry to paste into any other client")
        cmd.set_defaults(run=_install)

    sub.add_parser("clients", help="list supported AI clients and where they are installed"
                   ).set_defaults(run=_clients)

    login = sub.add_parser("login", help="log in to Kaggle or Hugging Face (once)")
    login.add_argument("platform", choices=["kaggle", "huggingface"])
    login.set_defaults(run=_login)

    doctor = sub.add_parser("doctor", help="check what is set up and what is still missing")
    doctor.add_argument("--online", action="store_true",
                        help="also check the Hugging Face login against the network")
    doctor.set_defaults(run=_doctor)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        return _serve(args)
    if args.command != "serve":
        # Never let an unusual console encoding turn a status message into a crash.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(errors="replace")
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
