"""Reinforcement-learning tools: env setup, reward curves, rollout video, seed sweeps.

Thin layer over the shared core: the heavy lifting (launch, poll, checkpoint) is
generic; RL only adds environment provisioning, reward plotting, episode rendering,
and multi-seed launches (RL results are seed-sensitive, so a defensible thesis
reports several seeds).
"""

import posixpath

from mcp.server.fastmcp import Image

from .. import runtime_state as rs
from . import _plots, hf_jobs
from .core import is_job, launch_impl


def register(mcp):
    @mcp.tool()
    def rl_setup(extras: str = "classic-control") -> str:
        """Install a standard RL stack on the runtime (Gymnasium + Stable-Baselines3 + imageio).

        extras: Gymnasium extras to include, e.g. "classic-control", "box2d", "atari,accept-rom-license".
        Also installs xvfb + pyvirtualdisplay for headless rendering.
        """
        packages = [f"gymnasium[{extras}]", "stable-baselines3", "imageio", "imageio-ffmpeg",
                    "pyvirtualdisplay"]
        code = (
            "import shutil, subprocess, sys\n"
            "if shutil.which('apt-get'):\n"
            "    subprocess.run(['apt-get', '-qq', 'install', '-y', 'xvfb'], capture_output=True)\n"
            f"r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', *{packages!r}], "
            "capture_output=True, text=True)\n"
            "if r.returncode != 0:\n    print('pip failed:', r.stderr[-1500:])\n"
            "import gymnasium, stable_baselines3\n"
            "print('gymnasium', gymnasium.__version__, 'sb3', stable_baselines3.__version__)\n"
        )
        return rs.jupyter.execute(code, timeout=600).text or "(setup finished)"

    @mcp.tool()
    @hf_jobs.hf_errors
    def rl_reward_curve(run_name: str) -> list:
        """Plot the reward curve for an RL run (auto-detects reward-like metric keys)."""
        run = rs.store.get_run(run_name)
        if not run:
            return [f"No run named '{run_name}'."]
        candidates = ["reward", "ep_reward", "ep_rew_mean", "return", "eval_return", "mean_reward"]
        if is_job(run):
            rows = hf_jobs.job_metric_rows(run)
            keys = [k for k in candidates if any(k in r for r in rows)]
            return [f"reward curve — keys {keys} rows {len(rows)}",
                    Image(data=_plots.plot_png(rows, keys, f"reward: {run_name}"), format="png")]
        rd = run["dir"]
        out_abs = posixpath.join(rd, "_reward.png")
        code = (
            "import json, os, matplotlib\nmatplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            f"rd = {rd!r}\ncand = {candidates!r}\n"
            "mp = os.path.join(rd,'metrics.jsonl')\n"
            "rows = [json.loads(l) for l in open(mp)] if os.path.exists(mp) else []\n"
            "keys = [k for k in cand if any(k in r for r in rows)]\n"
            "plt.figure(figsize=(7,4))\n"
            "for k in keys:\n"
            "    pts = [((r['step'] if r.get('step') is not None else i), r[k]) for i, r in enumerate(rows) if r.get(k) is not None]\n"
            "    if pts:\n        xs, ys = zip(*pts); plt.plot(xs, ys, label=k)\n"
            "plt.legend(); plt.xlabel('step'); plt.ylabel('reward'); plt.grid(alpha=0.3)\n"
            f"plt.title('reward: ' + {run_name!r})\n"
            f"plt.savefig({out_abs!r}, dpi=120, bbox_inches='tight')\n"
            "print('keys', keys, 'rows', len(rows))\n"
        )
        res = rs.jupyter.execute(code, timeout=60)
        if res.error:
            return [f"Failed:\n{res.error}"]
        try:
            data = rs.jupyter.download_bytes(rs.to_rel(out_abs))
        except Exception as e:  # noqa: BLE001
            return [f"Rendered but fetch failed: {e}\n{res.text}"]
        return [f"reward curve — {res.text.strip()}", Image(data=data, format="png")]

    @mcp.tool()
    def rl_record_rollout(run_name: str, rollout_code: str, max_frames: int = 16) -> list:
        """Render an episode and return a contact sheet of frames (and save a gif on the runtime).

        ``rollout_code`` runs on the runtime and MUST leave a variable ``frames`` — a list
        of HxWx3 uint8 arrays (e.g. from ``env.render()`` with render_mode='rgb_array').
        A ``rollout.gif`` is written to the run dir; download it with download_file.
        """
        run = rs.store.get_run(run_name)
        if not run:
            return [f"No run named '{run_name}'."]
        if is_job(run):
            return [f"'{run_name}' ran as a Hugging Face job, which has no live machine to render "
                    "on. Connect a runtime, load the policy from the run's Hub repo "
                    f"({run['hub_repo']}), and launch or register a run there."]
        rd = run["dir"]
        png_abs = posixpath.join(rd, "rollout.png")
        gif_abs = posixpath.join(rd, "rollout.gif")
        # Pillow only (it ships with matplotlib), so this works without rl_setup.
        wrapper = (
            "import math\nimport numpy as np\nfrom PIL import Image as _PILImage\n"
            "# ---- user rollout code (must define `frames`) ----\n"
            f"{rollout_code}\n"
            "# --------------------------------------------------\n"
            "frames = [np.asarray(f).astype('uint8')[..., :3] for f in frames]\n"
            "_imgs = [_PILImage.fromarray(f) for f in frames]\n"
            f"_imgs[0].save({gif_abs!r}, save_all=True, append_images=_imgs[1:], duration=66, loop=0)\n"
            f"sel = frames[:: max(1, len(frames)//{int(max_frames)})][:{int(max_frames)}]\n"
            "n = len(sel); cols = int(math.ceil(math.sqrt(n))); rows = int(math.ceil(n/cols))\n"
            "h, w = sel[0].shape[:2]\n"
            "sheet = np.zeros((rows*h, cols*w, 3), dtype='uint8')\n"
            "for i, fr in enumerate(sel):\n"
            "    r, c = divmod(i, cols)\n"
            "    sheet[r*h:(r+1)*h, c*w:(c+1)*w] = fr\n"
            f"_PILImage.fromarray(sheet).save({png_abs!r})\n"
            f"print('frames', len(frames), 'gif', {gif_abs!r})\n"
        )
        res = rs.jupyter.execute(wrapper, timeout=300)
        if res.error:
            return [f"Rollout failed:\n{res.error}"]
        try:
            data = rs.jupyter.download_bytes(rs.to_rel(png_abs))
        except Exception as e:  # noqa: BLE001
            return [f"Rendered but fetch failed: {e}\n{res.text}"]
        return [f"rollout — {res.text.strip()}", Image(data=data, format="png")]

    @mcp.tool()
    @hf_jobs.hf_errors
    def rl_seed_sweep(script: str, run_name: str, seeds: str, requirements: str = "",
                      hf_flavor: str = "", hf_timeout: str = "1h") -> str:
        """Launch the same training script across several seeds as separate runs.

        seeds: comma-separated, e.g. "0,1,2". Each becomes a run '<run_name>_s<seed>'
        with THESIS_SEED set (read it as ``SEED`` in your script). Poll each run by name.
        hf_flavor: leave empty to run all seeds on the connected runtime. Set a Hugging Face
                   machine type (e.g. "t4-small") to give every seed its own rented job,
                   so they train in parallel; each is billed separately, up to hf_timeout.
        """
        seed_list = [s.strip() for s in seeds.split(",") if s.strip()]
        if not seed_list:
            return "No seeds provided (e.g. seeds='0,1,2')."
        launched = []
        for s in seed_list:
            name = f"{run_name}_s{s}"
            env = {"THESIS_SEED": s}
            if hf_flavor:
                ok, msg = hf_jobs.launch_job_impl(script, name, hf_flavor, hf_timeout,
                                                  requirements, env)
            else:
                ok, _, msg = launch_impl(script, name, requirements, env)
            launched.append(f"{name}: {'ok' if ok else 'FAILED ' + msg}")
        return "Seed sweep launched:\n" + "\n".join(launched)
