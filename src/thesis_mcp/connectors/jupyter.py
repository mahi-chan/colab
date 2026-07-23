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
        self.base_url = url.rstrip("/")
        self.token = token
        self.kernel_id = ""

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
        r = requests.post(self._api("/api/kernels"), headers=self._headers, timeout=30)
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

        deadline = _time.time() + timeout
        try:
            ws.send(json.dumps(request))
            while _time.time() < deadline:
                try:
                    ws.settimeout(max(1.0, deadline - _time.time()))
                    raw = ws.recv()
                except WebSocketTimeoutException:
                    break
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
                elif mtype == "status" and content.get("execution_state") == "idle":
                    break
        finally:
            try:
                ws.close()
            except Exception:
                pass
        return res

    # -- files (Contents API) ----------------------------------------------
    def upload_bytes(self, remote_path: str, data: bytes) -> Dict[str, Any]:
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
        payload = {"type": "notebook", "format": "json", "content": nb}
        r = requests.put(
            self._api(f"/api/contents/{remote_path.lstrip('/')}"),
            headers=self._headers,
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        return r.json()
