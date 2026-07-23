"""Notebook tools: let the agent read and edit .ipynb cells on the runtime.

These operate on notebook files via the Jupyter Contents API and execute cells on
the live kernel — the "give the code agent access to edit Colab" basics. Paths are
relative to the runtime's contents root (e.g. ``notebooks/thesis.ipynb``).
"""

from mcp.server.fastmcp import Image

from .. import runtime_state as rs


def _new_cell(cell_type: str, source: str) -> dict:
    cell = {"cell_type": cell_type, "metadata": {}, "source": source}
    if cell_type == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    return cell


def _empty_notebook() -> dict:
    return {
        "cells": [],
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def register(mcp):
    @mcp.tool()
    def notebook_read(path: str) -> str:
        """Read a notebook and list its cells with indices, types, and source previews."""
        nb = rs.jupyter.notebook_get(path)
        lines = [f"{path} — {len(nb.get('cells', []))} cells"]
        for i, c in enumerate(nb.get("cells", [])):
            src = c.get("source", "")
            if isinstance(src, list):
                src = "".join(src)
            preview = src.strip().replace("\n", "\\n")
            if len(preview) > 100:
                preview = preview[:100] + "…"
            lines.append(f"[{i}] {c.get('cell_type'):8} | {preview}")
        return "\n".join(lines)

    @mcp.tool()
    def notebook_create(path: str) -> str:
        """Create a new empty notebook at ``path`` on the runtime."""
        rs.jupyter.notebook_put(path, _empty_notebook())
        return f"Created notebook {path}"

    @mcp.tool()
    def notebook_add_cell(path: str, source: str, cell_type: str = "code",
                          index: int = -1) -> str:
        """Add a cell to a notebook. index=-1 appends; otherwise inserts before that index."""
        nb = rs.jupyter.notebook_get(path)
        cell = _new_cell(cell_type, source)
        cells = nb.setdefault("cells", [])
        if index < 0 or index >= len(cells):
            cells.append(cell)
            pos = len(cells) - 1
        else:
            cells.insert(index, cell)
            pos = index
        rs.jupyter.notebook_put(path, nb)
        return f"Added {cell_type} cell at index {pos} in {path}"

    @mcp.tool()
    def notebook_edit_cell(path: str, index: int, source: str) -> str:
        """Replace the source of cell ``index`` in a notebook."""
        nb = rs.jupyter.notebook_get(path)
        cells = nb.get("cells", [])
        if not 0 <= index < len(cells):
            return f"Index {index} out of range (0..{len(cells)-1})."
        cells[index]["source"] = source
        if cells[index].get("cell_type") == "code":
            cells[index]["outputs"] = []
            cells[index]["execution_count"] = None
        rs.jupyter.notebook_put(path, nb)
        return f"Edited cell {index} in {path}"

    @mcp.tool()
    def notebook_delete_cell(path: str, index: int) -> str:
        """Delete cell ``index`` from a notebook."""
        nb = rs.jupyter.notebook_get(path)
        cells = nb.get("cells", [])
        if not 0 <= index < len(cells):
            return f"Index {index} out of range (0..{len(cells)-1})."
        removed = cells.pop(index)
        rs.jupyter.notebook_put(path, nb)
        return f"Deleted {removed.get('cell_type')} cell {index} from {path}"

    @mcp.tool()
    def notebook_run_cell(path: str, index: int, timeout: int = 120,
                          write_output: bool = True) -> list:
        """Execute a notebook cell's code on the kernel; optionally write outputs back.

        Returns stdout/results and any images. Only 'code' cells are executed.
        """
        nb = rs.jupyter.notebook_get(path)
        cells = nb.get("cells", [])
        if not 0 <= index < len(cells):
            return [f"Index {index} out of range (0..{len(cells)-1})."]
        cell = cells[index]
        if cell.get("cell_type") != "code":
            return [f"Cell {index} is '{cell.get('cell_type')}', not code."]
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        res = rs.jupyter.execute(source, timeout=timeout)

        if write_output:
            outputs = []
            if res.stdout:
                outputs.append({"output_type": "stream", "name": "stdout", "text": res.stdout})
            for r in res.results:
                outputs.append({"output_type": "execute_result", "data": {"text/plain": r},
                                "metadata": {}, "execution_count": None})
            if res.error:
                outputs.append({"output_type": "error", "ename": "Error", "evalue": "",
                                "traceback": res.error.splitlines()})
            cell["outputs"] = outputs
            rs.jupyter.notebook_put(path, nb)

        parts: list = [res.text or "(no output)"]
        parts.extend(Image(data=b, format="png") for b in res.images)
        return parts
