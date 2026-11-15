"""Stand-in for ``huggingface_hub`` on the test "remote machine".

The integration tests put this directory on the remote side's PYTHONPATH, so code
that uploads to the Hub from the runtime records what it would send instead of
needing the network. Each call is appended to the file named by ``HF_STUB_LOG``.
"""

import json
import os


def get_token():
    return os.environ.get("HF_TOKEN") or None


class HfApi:
    def _record(self, call, **details):
        with open(os.environ["HF_STUB_LOG"], "a") as f:
            f.write(json.dumps({"call": call, **details}) + "\n")

    def create_repo(self, repo_id, *, private=None, exist_ok=False, **_):
        self._record("create_repo", repo_id=repo_id, private=private)

    def upload_folder(self, *, folder_path, repo_id, path_in_repo=None, **_):
        files = sorted(
            os.path.relpath(os.path.join(root, name), folder_path)
            for root, _dirs, names in os.walk(folder_path) for name in names
        )
        self._record("upload_folder", repo_id=repo_id, path_in_repo=path_in_repo, files=files)

    def upload_file(self, *, path_or_fileobj, path_in_repo, repo_id, **_):
        self._record("upload_file", repo_id=repo_id, path_in_repo=path_in_repo)
