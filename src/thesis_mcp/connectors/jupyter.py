"""Client for a Jupyter Server running on the remote GPU machine.

On Colab/Kaggle the runtime starts a ``jupyter server`` and exposes it over a tunnel
(see ``runtime/colab_bootstrap.py``); on Hugging Face it runs inside a Job or Space
behind Hugging Face's own authentication. This client talks to that server:

* code execution on a kernel over the ``/api/kernels/{id}/channels`` WebSocket,
  capturing stdout, text results, and PNG images (plots, rendered frames);
* file upload/download and notebook read/write over the ``/api/contents`` REST
  API.

It needs only ``requests`` and ``websocket-client``: the heavy ML libraries live on
the remote machine, never on the computer running this server.
"""

import base64
import datetime as _dt
import json
import posixpath
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from websocket import WebSocketTimeoutException, create_connection


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


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
    """``bearer`` is a Hugging Face token: Jobs and private Spaces sit behind Hugging
    Face's proxy, which wants ``Authorization: Bearer <hf token>``. That header is then
    taken, so the Jupyter token travels as the ``token`` query parameter instead.
    """

    def __init__(self, url: str = "", token: str = "", kernel_id: str = "", bearer: str = ""):
        self.base_url = (url or "").rstrip("/")
        self.token = token or ""
        self.bearer = bearer or ""
        self.kernel_id = kernel_id or ""
        self.session_id = uuid.uuid4().hex

    # -- configuration ------------------------------------------------------
    def configure(self, url: str, token: str, bearer: str = "") -> None:
        url = url.rstrip("/")
        if url != self.base_url:
            self.kernel_id = ""  # kernel ids are per-server
        self.base_url = url
        self.token = token
        self.bearer = bearer

    def disconnect(self) -> None:
        self.base_url = self.token = self.bearer = self.kernel_id = ""

    @property
    def connected(self) -> bool:
        return bool(self.base_url)

    @property
    def _headers(self) -> Dict[str, str]:
        if self.bearer:
            return {"Authorization": f"Bearer {self.bearer}"}
        return {"Authorization": f"token {self.token}"} if self.token else {}

    @property
    def _auth_params(self) -> Dict[str, str]:
        return {"token": self.token} if self.bearer and self.token else {}

    def _api(self, path: str) -> str:
        if not self.base_url:
            raise RuntimeNotConnected(
                "No runtime connected. Colab/Kaggle: run the bootstrap cell, export "
                "JUPYTER_URL / JUPYTER_TOKEN, then call connect_runtime. "
                "Hugging Face: call hf_runtime_start, then hf_runtime_connect."
            )
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, *, timeout: int = 30,
                 params: Optional[Dict[str, Any]] = None, **kw: Any) -> requests.Response:
        return requests.request(
            method, self._api(path), headers=self._headers,
            params={**self._auth_params, **(params or {})}, timeout=timeout,
            # never forward the Hugging Face token to wherever a redirect points
            allow_redirects=not self.bearer, **kw,
        )

    def ping(self) -> bool:
        """True when the Jupyter server answers and accepts our credentials."""
        try:
            return self._request("GET", "/api/kernels", timeout=15).status_code == 200
        except requests.RequestException:
            return False

    # -- kernel lifecycle ---------------------------------------------------
    def start_kernel(self) -> str:
        # path="" starts the kernel in the server's root_dir (without it, the kernel
        # inherits the server process's cwd), so kernel-relative paths and Contents-API
        # paths refer to the same files.
        r = self._request("POST", "/api/kernels", json={"path": ""})
        r.raise_for_status()
        self.kernel_id = r.json()["id"]
        return self.kernel_id

    def list_kernels(self) -> List[Dict[str, Any]]:
        r = self._request("GET", "/api/kernels")
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
            self._request("POST", f"/api/kernels/{self.kernel_id}/interrupt")
        except requests.RequestException:
            pass

    def _ws_url(self) -> str:
        query = urlencode({"session_id": self.session_id, **self._auth_params})
        base = self._api(f"/api/kernels/{self.kernel_id}/channels") + "?" + query
        return base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)

    # -- execution ----------------------------------------------------------
    def execute(self, code: str, timeout: int = 120) -> ExecResult:
        """Run ``code`` on the kernel and collect its outputs until it goes idle."""
        self.ensure_kernel()
        ws = create_connection(
            self._ws_url(),
            header=self._headers,
            enable_multithread=True,
            timeout=timeout,
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

        def _pump(until: float) -> bool:
            """Read replies to our request until the kernel goes idle (True) or ``until``."""
            while time.time() < until:
                try:
                    ws.settimeout(max(1.0, until - time.time()))
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
            if not _pump(time.time() + timeout):
                # Don't leave the kernel busy: every later tool call would queue behind
                # the still-running code and time out too. Interrupt, then wait for the
                # interrupted cell to settle so the next request isn't aborted.
                self.interrupt_kernel()
                _pump(time.time() + 15)
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
            path = f"/api/contents/{sub}"
            if self._request("GET", path, params={"content": 0}).ok:
                continue
            self._request("PUT", path, json={"type": "directory"}).raise_for_status()

    def upload_bytes(self, remote_path: str, data: bytes) -> Dict[str, Any]:
        self.ensure_dir(posixpath.dirname(remote_path.lstrip("/")))
        payload = {
            "type": "file",
            "format": "base64",
            "content": base64.b64encode(data).decode(),
        }
        r = self._request("PUT", f"/api/contents/{remote_path.lstrip('/')}",
                          json=payload, timeout=300)
        r.raise_for_status()
        return r.json()

    def download_bytes(self, remote_path: str) -> bytes:
        r = self._request("GET", f"/api/contents/{remote_path.lstrip('/')}",
                          params={"format": "base64"}, timeout=300)
        r.raise_for_status()
        return base64.b64decode(r.json()["content"])

    # -- notebooks ----------------------------------------------------------
    def notebook_get(self, remote_path: str) -> Dict[str, Any]:
        r = self._request("GET", f"/api/contents/{remote_path.lstrip('/')}",
                          params={"type": "notebook"}, timeout=60)
        r.raise_for_status()
        return r.json()["content"]

    def notebook_put(self, remote_path: str, nb: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_dir(posixpath.dirname(remote_path.lstrip("/")))
        payload = {"type": "notebook", "format": "json", "content": nb}
        r = self._request("PUT", f"/api/contents/{remote_path.lstrip('/')}",
                          json=payload, timeout=60)
        r.raise_for_status()
        return r.json()
