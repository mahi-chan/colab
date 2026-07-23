"""Reinforcement-learning tools: env setup, reward curves, rollout video, seed sweeps.

Thin layer over the shared core: the heavy lifting (launch, poll, checkpoint) is
generic; RL only adds environment provisioning, reward plotting, episode rendering,
and multi-seed launches (RL results are seed-sensitive, so a defensible thesis
reports several seeds).
"""

import posixpath

from mcp.server.fastmcp import Image

from .. import runtime_state as rs
from .core import launch_impl


def register(mcp):
    @mcp.tool()
    def rl_setup(extras: str = "classic-control") -> str:
        """Install a standard RL stack on the runtime (Gymnasium + Stable-Baselines3 + imageio).

        extras: Gymnasium extras to include, e.g. "classic-control", "box2d", "atari,accept-rom-license".
        Also installs xvfb + pyvirtualdisplay for headless rendering.
        """
        code = (
            "import subprocess\n"
            "subprocess.run('apt-get -qq install -y xvfb'.split(), check=False)\n"
            f"subprocess.run('pip -q install gymnasium[{extras}] stable-baselines3 "
            "imageio imageio-ffmpeg pyvirtualdisplay'.split(), check=False)\n"
            "import gymnasium, stable_baselines3\n"
            "print('gymnasium', gymnasium.__version__, 'sb3', stable_baselines3.__version__)\n"
        )
        return rs.jupyter.execute(code, timeout=600).text or "(setup finished)"

    @mcp.tool()
    def rl_reward_curve(run_name: str) -> list:
        """Plot the reward curve for an RL run (auto-detects reward-like metric keys)."""
        run = rs.store.get_run(run_name)
        if not run:
            return [f"No run named '{run_name}'."]
        rd = run["dir"]
        out_abs = posixpath.join(rd, "_reward.png")
        candidates = ["reward", "ep_reward", "ep_rew_mean", "return", "eval_return", "mean_reward"]
        code = (
            "import json, os, matplotlib\nmatplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            f"rd = {rd!r}\ncand = {candidates!r}\n"
            "mp = os.path.join(rd,'metrics.jsonl')\n"
            "rows = [json.loads(l) for l in open(mp)] if os.path.exists(mp) else []\n"
            "keys = [k for k in cand if any(k in r for r in rows)]\n"
            "plt.figure(figsize=(7,4))\n"
            "for k in keys:\n"
            "    pts = [(r.get('step', i), r[k]) for i, r in enumerate(rows) if r.get(k) is not None]\n"
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
        rd = run["dir"]
        png_abs = posixpath.join(rd, "rollout.png")
        gif_abs = posixpath.join(rd, "rollout.gif")
        wrapper = (
            "import numpy as np, imageio, math, os\n"
            "# ---- user rollout code (must define `frames`) ----\n"
            f"{rollout_code}\n"
            "# --------------------------------------------------\n"
            "frames = [np.asarray(f).astype('uint8') for f in frames]\n"
            f"imageio.mimsave({gif_abs!r}, frames, fps=15)\n"
            f"sel = frames[:: max(1, len(frames)//{int(max_frames)})][:{int(max_frames)}]\n"
            "n = len(sel); cols = int(math.ceil(math.sqrt(n))); rows = int(math.ceil(n/cols))\n"
            "h, w = sel[0].shape[:2]\n"
            "sheet = np.zeros((rows*h, cols*w, 3), dtype='uint8')\n"
            "for i, fr in enumerate(sel):\n"
            "    r, c = divmod(i, cols)\n"
            "    sheet[r*h:(r+1)*h, c*w:(c+1)*w] = fr[..., :3]\n"
            f"imageio.imwrite({png_abs!r}, sheet)\n"
            "print('frames', len(frames), 'gif', " f"{gif_abs!r}" ")\n"
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
    def rl_seed_sweep(script: str, run_name: str, seeds: str,
                      requirements: str = "") -> str:
        """Launch the same training script across several seeds as separate runs.

        seeds: comma-separated, e.g. "0,1,2". Each becomes a run '<run_name>_s<seed>'
        with THESIS_SEED set (read it as ``SEED`` in your script). Poll each run by name.
        """
        seed_list = [s.strip() for s in seeds.split(",") if s.strip()]
        if not seed_list:
            return "No seeds provided (e.g. seeds='0,1,2')."
        launched = []
        for s in seed_list:
            name = f"{run_name}_s{s}"
            ok, _, msg = launch_impl(script, name, requirements, {"THESIS_SEED": s})
            launched.append(f"{name}: {'ok' if ok else 'FAILED ' + msg}")
        return "Seed sweep launched:\n" + "\n".join(launched)
