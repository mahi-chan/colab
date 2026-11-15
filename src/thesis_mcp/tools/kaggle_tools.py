"""Kaggle competition and dataset tools.

They run on this computer when the user is logged in to Kaggle here (so they work with
no runtime at all, and with any runtime), and otherwise through the Kaggle command line
on the connected runtime, which is logged in automatically inside Kaggle.
"""

import os
import posixpath
import tempfile

from .. import runtime_state as rs
from ..connectors import kaggle_api


# Remote snippet: make sure the Kaggle CLI can run, then define _kaggle(args) -> CompletedProcess.
# `six` is installed alongside it because Kaggle CLI 2.x imports it without declaring it.
# The CLI is started as `python -m kaggle` so it always uses the kernel's own environment.
KAGGLE_SNIPPET = '''\
import importlib.util as _ilu, subprocess as _sp, sys as _sys
if _ilu.find_spec("kaggle") is None or _ilu.find_spec("six") is None:
    _sp.run([_sys.executable, "-m", "pip", "install", "-q", "kaggle", "six"], check=False)
def _kaggle(args, env=None):
    import os as _os
    return _sp.run([_sys.executable, "-m", "kaggle", *args], capture_output=True, text=True,
                   env={**_os.environ, **(env or {})})
'''


def run_kaggle(args: list, timeout: int = 300) -> str:
    if kaggle_api.logged_in():
        return kaggle_api.cli(args, timeout=timeout)
    if not rs.jupyter.connected:
        return kaggle_api.LOGIN_HELP
    code = (
        KAGGLE_SNIPPET
        + f"_r = _kaggle({args!r})\n"
        "print(_r.stdout.strip())\n"
        "if _r.stderr.strip(): print('[stderr]', _r.stderr.strip())\n"
    )
    return rs.jupyter.execute(code, timeout=timeout).text or "(no output)"


def register(mcp):
    @mcp.tool()
    def kaggle_submit(competition: str, file: str, message: str = "via thesis-mcp") -> str:
        """Submit a file to a competition.

        file: a path on this computer, or a path on the connected runtime (for example a
        run's submission.csv), which is fetched first.
        """
        if kaggle_api.logged_in() and not os.path.exists(file):
            if not rs.jupyter.connected:
                return f"No file {file!r} on this computer, and no runtime is connected to fetch it from."
            local = os.path.join(tempfile.mkdtemp(prefix="thesis-mcp-submit-"), posixpath.basename(file))
            with open(local, "wb") as f:
                f.write(rs.jupyter.download_bytes(rs.to_rel(file)))
            file = local
        return run_kaggle(["competitions", "submit", "-c", competition, "-f", file, "-m", message])

    @mcp.tool()
    def kaggle_submissions(competition: str) -> str:
        """List your recent submissions and their scores for a competition."""
        return run_kaggle(["competitions", "submissions", "-c", competition])

    @mcp.tool()
    def kaggle_leaderboard(competition: str) -> str:
        """Show the top of a competition's public leaderboard."""
        return run_kaggle(["competitions", "leaderboard", "-c", competition, "--show"])

    @mcp.tool()
    def kaggle_competition_files(competition: str) -> str:
        """List the downloadable files for a competition."""
        return run_kaggle(["competitions", "files", "-c", competition])

    @mcp.tool()
    def kaggle_search_datasets(query: str) -> str:
        """Search Kaggle datasets by keyword (returns refs usable with cv_load_dataset)."""
        return run_kaggle(["datasets", "list", "-s", query])
