"""Render metric curves locally, for runs whose metrics are not on a Jupyter runtime."""

import io
from typing import Any, Dict, List

from matplotlib.figure import Figure  # object API: no pyplot, no global backend state


def series(rows: List[Dict[str, Any]], key: str):
    """(x, y) points for one metric; rows logged without a step use their row index."""
    pts = [((r["step"] if r.get("step") is not None else i), r[key])
           for i, r in enumerate(rows) if isinstance(r.get(key), (int, float))]
    return zip(*pts, strict=True) if pts else ((), ())


def plot_png(rows: List[Dict[str, Any]], keys: List[str], title: str) -> bytes:
    fig = Figure(figsize=(7, 4))
    ax = fig.subplots()
    drawn = False
    for key in keys:
        xs, ys = series(rows, key)
        if xs:
            ax.plot(xs, ys, label=key, marker=".")
            drawn = True
    if drawn:
        ax.legend()
    ax.set_xlabel("step")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    return buf.getvalue()
