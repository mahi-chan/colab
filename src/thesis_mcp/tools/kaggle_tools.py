"""Kaggle competition/dataset tools, executed via the Kaggle CLI on the runtime.

Running on the runtime means submission files (already produced there by training)
never have to round-trip through your laptop, and no Kaggle credentials are needed
locally — only on the runtime (set in the bootstrap cell, automatic on Kaggle).
"""

from .. import runtime_state as rs


# Remote snippet: make sure the Kaggle CLI can run, then define _kaggle(args) -> CompletedProcess.
# `six` is installed alongside it because Kaggle CLI 2.x imports it without declaring it.
# The CLI is started as `python -m kaggle` so it always uses the kernel's own environment.
KAGGLE_SNIPPET = '''\
import importlib.util as _ilu, subprocess as _sp, sys as _sys
if _ilu.find_spec("kaggle") is None or _ilu.find_spec("six") is None:
    _sp.run([_sys.executable, "-m", "pip", "install", "-q", "kaggle", "six"], check=False)
def _kaggle(args):
    return _sp.run([_sys.executable, "-m", "kaggle", *args], capture_output=True, text=True)
'''


def run_kaggle(args: list, timeout: int = 300) -> str:
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
        """Submit a file (path on the runtime, e.g. a run's submission.csv) to a competition."""
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
