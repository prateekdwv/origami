"""Atomic local cache and single-writer manifest. Never contains credentials."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

from settings import DAY


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
        temporary = stream.name
    os.replace(temporary, path)


class Store:
    def __init__(self, directory):
        self.root = Path(directory)
        self.path = self.root / "manifest.json"
        self.manifest = json.loads(self.path.read_text()) if self.path.exists() else {
            "version": 1, "day": DAY, "requests": [], "selection": [],
            "gate": "not_checked", "passes": {}, "budget_total": 90,
        }
        if self.manifest["day"] != DAY:
            raise ValueError("Cache belongs to another replay day")

    def save(self):
        write_json(self.path, self.manifest)

    def response(self, record):
        return json.loads((self.root / record["file"]).read_text())["payload"]

    def successful(self, kind, identity):
        return [r for r in self.manifest["requests"]
                if r["kind"] == kind and r["identity"] == identity and r["status"] == "ok"]

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another acquisition/preparation process holds the cache lock") from None
            # Reload after obtaining the lock; recover responses saved before a crash.
            if self.path.exists():
                self.manifest = json.loads(self.path.read_text())
            for record in self.manifest["requests"]:
                if record["status"] == "inflight" and (self.root / record["file"]).exists():
                    record["status"] = "ok"
            staged = self.root / "prepared.staged.json"
            if staged.exists() and not (self.root / "prepared.json").exists() and self.manifest.get("frozen_sha256"):
                if hashlib.sha256(staged.read_bytes()).hexdigest() != self.manifest["frozen_sha256"]:
                    raise RuntimeError("Interrupted frozen dataset has invalid hash")
                staged.replace(self.root / "prepared.json")
            yield self
