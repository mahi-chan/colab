"""Client for a Jupyter Server running inside a Colab/Kaggle VM.

The runtime (Colab or Kaggle) starts a ``jupyter server`` and exposes it over a
tunnel (see ``runtime/colab_bootstrap.py``). This client talks to that server:

* code execution on a kernel over the ``/api/kernels/{id}/channels`` WebSocket,
  capturing stdout, text results, and PNG images (plots, rendered frames);
* file upload/download and notebook read/write over the ``/api/contents`` REST
  API.

It is intentionally dependency-light (``requests`` + ``websocket-client``) so the
*local* install stays tiny — all the heavy ML libraries live on the runtime.
"""

import base64
import datetime as _dt
import json
import posixpath
import ssl
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from websocket import WebSocketTimeoutException, create_connection


def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat() + "Z"


@dataclass
class ExecResult:
    stdout: str = ""
    results: List[str] = field(default_factory=list)  # text/plain outputs
    images: List[bytes] = field(default_factory=list)  # decoded PNG bytes
    error: Optional[str] = None                        # traceback, if any

    @property
    def text(self) -> str:
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.rstrip())
        parts.extend(r for r in self.results if r.strip())
        if self.error:
            parts.append("[ERROR]\n" + self.error)
        return "\n".join(parts).strip()


class RuntimeNotConnected(RuntimeError):
    pass


class JupyterClient:
    def __init__(self, url: str = "", token: str = "", kernel_id: str = ""):
        self.base_url = (url or "").rstrip("/")
        self.token = token or ""
        self.kernel_id = kernel_id or ""
        self.session_id = uuid.uuid4().hex

    # -- configuration ------------------------------------------------------
    def configure(self, url: str, token: str) -> None:
        url = url.rstrip("/")
        if url != self.base_url:
            self.kernel_id = ""  # kernel ids are per-server
        self.base_url = url
        self.token = token

    @property
    def connected(self) -> bool:
        return bool(self.base_url)

    @property
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"token {self.token}"} if self.token else {}

    def _api(self, path: str) -> str:
        if not self.base_url:
            raise RuntimeNotConnected(
                "No runtime connected. Run the Colab/Kaggle bootstrap cell, export "
                "JUPYTER_URL / JUPYTER_TOKEN, then call connect_runtime."
            )
        return f"{self.base_url}{path}"

    # -- kernel lifecycle ---------------------------------------------------
    def start_kernel(self) -> str:
        # path="" starts the kernel in the server's root_dir (without it, the kernel
        # inherits the server process's cwd), so kernel-relative paths and Contents-API
        # paths refer to the same files.
        r = requests.post(self._api("/api/kernels"), headers=self._headers,
                          json={"path": ""}, timeout=30)
        r.raise_for_status()
        self.kernel_id = r.json()["id"]
        return self.kernel_id

    def list_kernels(self) -> List[Dict[str, Any]]:
        r = requests.get(self._api("/api/kernels"), headers=self._headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def kernel_alive(self) -> bool:
        if not self.kernel_id:
            return False
        try:
            return any(k["id"] == self.kernel_id for k in self.list_kernels())
        except requests.RequestException:
            return False

    def ensure_kernel(self) -> str:
        if self.kernel_alive():
            return self.kernel_id
        return self.start_kernel()

    def interrupt_kernel(self) -> None:
        try:
            requests.post(self._api(f"/api/kernels/{self.kernel_id}/interrupt"),
                          headers=self._headers, timeout=30)
        except requests.RequestException:
            pass

    def _ws_url(self) -> str:
        base = self._api(f"/api/kernels/{self.kernel_id}/channels")
        return base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)

    # -- execution ----------------------------------------------------------
    def execute(self, code: str, timeout: int = 120) -> ExecResult:
        """Run ``code`` on the kernel and collect its outputs until it goes idle."""
        self.ensure_kernel()
        ws = create_connection(
            self._ws_url(),
            header=[f"Authorization: token {self.token}"],
            enable_multithread=True,
            timeout=timeout,
            sslopt={"cert_reqs": ssl.CERT_REQUIRED},
        )
        msg_id = uuid.uuid4().hex
        request = {
            "header": {
                "msg_id": msg_id,
                "username": "thesis-mcp",
                "session": self.session_id,
                "msg_type": "execute_request",
                "version": "5.3",
                "date": _now_iso(),
            },
            "parent_header": {},
            "metadata": {},
            "content": {
                "code": code,
                "silent": False,
                "store_history": True,
                "user_expressions": {},
                "allow_stdin": False,
                "stop_on_error": True,
            },
            "channel": "shell",
            "buffers": [],
        }
        res = ExecResult()
        import time as _time

        def _pump(until: float) -> bool:
            """Read replies to our request until the kernel goes idle (True) or ``until``."""
            while _time.time() < until:
                try:
                    ws.settimeout(max(1.0, until - _time.time()))
                    raw = ws.recv()
                except WebSocketTimeoutException:
                    return False
                if not raw:
                    continue
                msg = json.loads(raw)
                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue  # not a reply to our request
                mtype = msg.get("header", {}).get("msg_type")
                content = msg.get("content", {})
                if mtype == "stream":
                    res.stdout += content.get("text", "")
                elif mtype in ("execute_result", "display_data"):
                    data = content.get("data", {})
                    if "image/png" in data:
                        try:
                            res.images.append(base64.b64decode(data["image/png"]))
                        except (ValueError, TypeError):
                            pass
                    if "text/plain" in data:
                        res.results.append(data["text/plain"])
                elif mtype == "error":
                    res.error = "\n".join(content.get("traceback", [])) or content.get("evalue")
                elif mtype == "execute_reply" and content.get("status") == "aborted":
                    res.error = res.error or "Execution aborted by the kernel (a previous cell errored or was interrupted); retry."
                elif mtype == "status" and content.get("execution_state") == "idle":
                    return True
            return False

        try:
            ws.send(json.dumps(request))
            if not _pump(_time.time() + timeout):
                # Don't leave the kernel busy: every later tool call would queue behind
                # the still-running code and time out too. Interrupt, then wait for the
                # interrupted cell to settle so the next request isn't aborted.
                self.interrupt_kernel()
                _pump(_time.time() + 15)
                timeout_msg = (f"Execution timed out after {timeout}s; the kernel was interrupted. "
                               "Use launch_training for long-running work.")
                res.error = f"{res.error}\n{timeout_msg}" if res.error else timeout_msg
        finally:
            try:
                ws.close()
            except Exception:
                pass
        return res

    # -- files (Contents API) ----------------------------------------------
    def ensure_dir(self, remote_dir: str) -> None:
        """Create ``remote_dir`` and its parents (the Contents API won't write into a missing dir)."""
        parts = [p for p in remote_dir.strip("/").split("/") if p]
        for i in range(1, len(parts) + 1):
            sub = "/".join(parts[:i])
            url = self._api(f"/api/contents/{sub}")
            if requests.get(url, headers=self._headers, params={"content": 0}, timeout=30).ok:
                continue
            r = requests.put(url, headers=self._headers, json={"type": "directory"}, timeout=30)
            r.raise_for_status()

    def upload_bytes(self, remote_path: str, data: bytes) -> Dict[str, Any]:
        self.ensure_dir(posixpath.dirname(remote_path.lstrip("/")))
        payload = {
            "type": "file",
            "format": "base64",
            "content": base64.b64encode(data).decode(),
        }
        r = requests.put(
            self._api(f"/api/contents/{remote_path.lstrip('/')}"),
            headers=self._headers,
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        return r.json()

    def download_bytes(self, remote_path: str) -> bytes:
        r = requests.get(
            self._api(f"/api/contents/{remote_path.lstrip('/')}"),
            headers=self._headers,
            params={"format": "base64"},
            timeout=120,
        )
        r.raise_for_status()
        return base64.b64decode(r.json()["content"])

    # -- notebooks ----------------------------------------------------------
    def notebook_get(self, remote_path: str) -> Dict[str, Any]:
        r = requests.get(
            self._api(f"/api/contents/{remote_path.lstrip('/')}"),
            headers=self._headers,
            params={"type": "notebook"},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["content"]

    def notebook_put(self, remote_path: str, nb: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_dir(posixpath.dirname(remote_path.lstrip("/")))
        payload = {"type": "notebook", "format": "json", "content": nb}
        r = requests.put(
            self._api(f"/api/contents/{remote_path.lstrip('/')}"),
            headers=self._headers,
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        return r.json()
