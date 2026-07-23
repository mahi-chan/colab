"""Kaggle competition/dataset tools, executed via the Kaggle CLI on the runtime.

Running on the runtime means submission files (already produced there by training)
never have to round-trip through your laptop, and no Kaggle credentials are needed
locally — only on the runtime (set in the bootstrap cell, automatic on Kaggle).
"""

from .. import runtime_state as rs


def _kaggle(args_repr: str, timeout: int = 300) -> str:
    code = (
        "import subprocess\n"
        "subprocess.run('pip -q install kaggle'.split(), check=False)\n"
        f"r = subprocess.run(['kaggle', *{args_repr}], capture_output=True, text=True)\n"
        "print(r.stdout.strip()); \n"
        "if r.stderr.strip(): print('[stderr]', r.stderr.strip())\n"
    )
    return rs.jupyter.execute(code, timeout=timeout).text or "(no output)"


def register(mcp):
    @mcp.tool()
    def kaggle_submit(competition: str, file: str, message: str = "via thesis-mcp") -> str:
        """Submit a file (path on the runtime, e.g. a run's submission.csv) to a competition."""
        return _kaggle(["competitions", "submit", "-c", competition,
                        "-f", file, "-m", message].__repr__())

    @mcp.tool()
    def kaggle_submissions(competition: str) -> str:
        """List your recent submissions and their scores for a competition."""
        return _kaggle(["competitions", "submissions", "-c", competition].__repr__())

    @mcp.tool()
    def kaggle_leaderboard(competition: str) -> str:
        """Show the top of a competition's public leaderboard."""
        return _kaggle(["competitions", "leaderboard", "-c", competition, "--show"].__repr__())

    @mcp.tool()
    def kaggle_competition_files(competition: str) -> str:
        """List the downloadable files for a competition."""
        return _kaggle(["competitions", "files", "-c", competition].__repr__())

    @mcp.tool()
    def kaggle_search_datasets(query: str) -> str:
        """Search Kaggle datasets by keyword (returns refs usable with cv_load_dataset)."""
        return _kaggle(["datasets", "list", "-s", query].__repr__())
