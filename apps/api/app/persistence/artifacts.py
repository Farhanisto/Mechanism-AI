import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.mechanism.schemas import ArtifactManifestEntry
from app.persistence.metadata import MetadataStore

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_ARTIFACT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ArtifactStore:
    def __init__(self, root: Path, metadata: MetadataStore | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata = metadata
        self._writes: dict[tuple[str, str], ArtifactManifestEntry] = {}

    def run_dir(self, run_id: str) -> Path:
        if not _RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError(f"Invalid run id: {run_id!r}")
        path = self.root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, run_id: str, name: str, payload: Any) -> Path:
        self._validate_name(name)
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        text = json.dumps(payload, indent=2) + "\n"
        path = self.run_dir(run_id) / name
        handle, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                file.write(text)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        entry = ArtifactManifestEntry(
            name=name,
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            size_bytes=len(text.encode("utf-8")),
            written_at=datetime.now(UTC).isoformat(),
        )
        self._writes[(run_id, name)] = entry
        if self.metadata is not None:
            self.metadata.record_artifact(run_id, entry)
        return path

    def manifest(self, run_id: str) -> list[ArtifactManifestEntry]:
        entries = [
            entry for (stored_run, _), entry in self._writes.items() if stored_run == run_id
        ]
        return sorted(entries, key=lambda entry: entry.name)

    def write_bytes(self, run_id: str, name: str, data: bytes) -> Path:
        self._validate_name(name)
        path = self.run_dir(run_id) / name
        handle, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(data)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        entry = ArtifactManifestEntry(
            name=name,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            written_at=datetime.now(UTC).isoformat(),
        )
        self._writes[(run_id, name)] = entry
        if self.metadata is not None:
            self.metadata.record_artifact(run_id, entry)
        return path

    def read_bytes(self, run_id: str, name: str) -> bytes | None:
        self._validate_name(name)
        path = self.run_dir(run_id) / name
        if not path.is_file():
            return None
        return path.read_bytes()

    def read_json(self, run_id: str, name: str) -> Any | None:
        self._validate_name(name)
        path = self.run_dir(run_id) / name
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _validate_name(name: str) -> None:
        if not _ARTIFACT_NAME_PATTERN.fullmatch(name) or ".." in name:
            raise ValueError(f"Invalid artifact name: {name!r}")
