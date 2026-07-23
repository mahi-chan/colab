"""Computer-vision tools: dataset loading, training curves, prediction visualization.

Kaggle competition/dataset download runs *on the runtime* (where the GPU and disk
are), so big data never round-trips through your laptop. Submission + leaderboard
live in kaggle_tools.
"""

import posixpath

from mcp.server.fastmcp import Image

from .. import runtime_state as rs


def register(mcp):
    @mcp.tool()
    def cv_load_dataset(ref: str, dest: str = "data", kind: str = "dataset",
                        unzip: bool = True) -> str:
        """Download a Kaggle dataset or competition onto the runtime and unzip it.

        ref:  "owner/dataset-slug" for datasets, or the competition slug for competitions.
        kind: "dataset" or "competition".
        Requires Kaggle credentials on the runtime (set in the bootstrap cell, or
        automatic on Kaggle notebooks).
        """
        sub = "datasets download -d" if kind == "dataset" else "competitions download -c"
        code = (
            "import os, subprocess, glob, zipfile\n"
            f"dest = {dest!r}\nos.makedirs(dest, exist_ok=True)\n"
            "subprocess.run('pip -q install kaggle'.split(), check=False)\n"
            f"sub = {sub!r}\n"
            f"r = subprocess.run(['kaggle', *sub.split(), {ref!r}, '-p', dest], "
            "capture_output=True, text=True)\n"
            "print(r.stdout.strip()); print(r.stderr.strip())\n"
            + (
                "for z in glob.glob(os.path.join(dest,'*.zip')):\n"
                "    zipfile.ZipFile(z).extractall(dest)\n"
                if unzip else ""
            )
            + "print('CONTENTS', os.listdir(dest)[:30])\n"
        )
        return rs.jupyter.execute(code, timeout=900).text or "(no output)"

    @mcp.tool()
    def cv_training_curves(run_name: str) -> list:
        """Plot standard CV metrics for a run (loss / accuracy / mAP / IoU — auto-detected)."""
        run = rs.store.get_run(run_name)
        if not run:
            return [f"No run named '{run_name}'."]
        rd = run["dir"]
        out_abs = posixpath.join(rd, "_cv.png")
        candidates = ["loss", "val_loss", "acc", "val_acc", "top1", "top5",
                      "map", "mAP", "map50", "iou", "dice", "f1"]
        code = (
            "import json, os, matplotlib\nmatplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            f"rd = {rd!r}\ncand = {candidates!r}\n"
            "mp = os.path.join(rd,'metrics.jsonl')\n"
            "rows = [json.loads(l) for l in open(mp)] if os.path.exists(mp) else []\n"
            "keys = [k for k in cand if any(k in r for r in rows)]\n"
            "fig, ax = plt.subplots(1, 2, figsize=(11,4))\n"
            "for k in keys:\n"
            "    pts = [(r.get('step', i), r[k]) for i, r in enumerate(rows) if r.get(k) is not None]\n"
            "    if not pts:\n        continue\n"
            "    xs, ys = zip(*pts); a = ax[0] if 'loss' in k else ax[1]; a.plot(xs, ys, label=k)\n"
            "ax[0].set_title('loss'); ax[1].set_title('metrics')\n"
            "for a in ax:\n    a.legend(); a.grid(alpha=0.3); a.set_xlabel('step')\n"
            f"fig.suptitle({run_name!r}); fig.savefig({out_abs!r}, dpi=120, bbox_inches='tight')\n"
            "print('keys', keys, 'rows', len(rows))\n"
        )
        res = rs.jupyter.execute(code, timeout=60)
        if res.error:
            return [f"Failed:\n{res.error}"]
        try:
            data = rs.jupyter.download_bytes(rs.to_rel(out_abs))
        except Exception as e:  # noqa: BLE001
            return [f"Rendered but fetch failed: {e}\n{res.text}"]
        return [f"training curves — {res.text.strip()}", Image(data=data, format="png")]

    @mcp.tool()
    def cv_show_predictions(inference_code: str, out: str = "preds.png") -> list:
        """Run inference/visualization code on the runtime and show the saved image inline.

        ``inference_code`` runs on the runtime and should save its visualization
        (predictions, bounding boxes, masks, Grad-CAM, a batch grid…) to the path in the
        injected variable ``OUT``. Example last line: ``plt.savefig(OUT)`` or
        ``cv2.imwrite(OUT, canvas)``.
        """
        out_abs = posixpath.join(rs.contents_root(), out)
        code = f"OUT = {out_abs!r}\n# ---- user inference code ----\n{inference_code}\n"
        res = rs.jupyter.execute(code, timeout=300)
        if res.error:
            return [f"Inference failed:\n{res.error}"]
        try:
            data = rs.jupyter.download_bytes(rs.to_rel(out_abs))
        except Exception as e:  # noqa: BLE001
            return [f"Ran but could not fetch {out}: {e}\n{res.text}"]
        ext = out.rsplit(".", 1)[-1] if "." in out else "png"
        fmt = "jpeg" if ext.lower() in ("jpg", "jpeg") else ext.lower()
        return [res.text.strip() or "predictions", Image(data=data, format=fmt)]
