"""Local, on-disk state: the remembered kernel connection and the run registry.

This is what makes the server survive ``/clear`` and Claude Code restarts: the
Colab kernel keeps running in the cloud, and this file remembers its id + the
runs we launched so a fresh session can re-attach instead of starting over.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional


class RunStore:
    def __init__(self, state_dir: str):
        self.dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.path = os.path.join(state_dir, "state.json")
        self.data: Dict[str, Any] = {"kernel": {}, "runs": {}}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.data = {"kernel": {}, "runs": {}}
        self.data.setdefault("kernel", {})
        self.data.setdefault("runs", {})

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    # -- kernel / connection ------------------------------------------------
    def save_kernel(self, **kw: Any) -> None:
        self.data["kernel"].update(kw)
        self._save()

    def get_kernel(self) -> Dict[str, Any]:
        return self.data.get("kernel", {})

    def clear_kernel(self) -> None:
        self.data["kernel"] = {}
        self._save()

    # -- runs ---------------------------------------------------------------
    def new_run(self, name: str, run_dir: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        run = {
            "name": name,
            "dir": run_dir,
            "status": "created",
            "created": time.time(),
            **(meta or {}),
        }
        self.data["runs"][name] = run
        self._save()
        return run

    def update_run(self, name: str, **kw: Any) -> None:
        if name in self.data["runs"]:
            self.data["runs"][name].update(kw)
            self._save()

    def get_run(self, name: str) -> Optional[Dict[str, Any]]:
        return self.data["runs"].get(name)

    def list_runs(self) -> List[Dict[str, Any]]:
        return list(self.data["runs"].values())
