import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_ARTIFACT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

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
        path = self.run_dir(run_id) / name
        handle, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2)
                file.write("\n")
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        return path

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
