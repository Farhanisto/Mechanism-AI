"""SQLite metadata alongside the JSON artifacts (PRD §9.8).

Every run, candidate and artifact write is mirrored into a small SQLite
database so outcomes can be queried and reconstructed without walking the
JSON files. The JSON artifacts remain the authoritative evidence; this store
records the same facts plus artifact hashes and timestamps.
"""

import json
import sqlite3
from pathlib import Path

from app.mechanism.schemas import (
    ArtifactManifestEntry,
    CandidateRecord,
    DesignRun,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    error_code TEXT,
    no_pass INTEGER NOT NULL DEFAULT 0,
    final_candidate_id TEXT,
    prompt TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
    run_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (run_id, candidate_id)
);
CREATE TABLE IF NOT EXISTS artifacts (
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    written_at TEXT NOT NULL,
    PRIMARY KEY (run_id, name)
);
"""


class MetadataStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def record_run(self, run: DesignRun) -> None:
        self._connection.execute(
            """
            INSERT OR REPLACE INTO runs
            (run_id, status, stage, error_code, no_pass, final_candidate_id,
             prompt, created_at, updated_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.status.value,
                run.stage.value,
                run.error_code,
                int(run.no_pass),
                run.final_candidate_id,
                run.original_prompt,
                run.created_at.isoformat(),
                run.updated_at.isoformat(),
                run.model_dump_json(),
            ),
        )
        self._connection.commit()

    def record_candidate(self, run_id: str, record: CandidateRecord) -> None:
        self._connection.execute(
            """
            INSERT OR REPLACE INTO candidates
            (run_id, candidate_id, attempt_number, payload)
            VALUES (?, ?, ?, ?)
            """,
            (
                run_id,
                record.candidate.candidate_id,
                record.candidate.attempt_number,
                record.model_dump_json(),
            ),
        )
        self._connection.commit()

    def record_artifact(self, run_id: str, entry: ArtifactManifestEntry) -> None:
        self._connection.execute(
            """
            INSERT OR REPLACE INTO artifacts
            (run_id, name, sha256, size_bytes, written_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, entry.name, entry.sha256, entry.size_bytes, entry.written_at),
        )
        self._connection.commit()

    def get_run(self, run_id: str) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list_candidate_payloads(self, run_id: str) -> list[dict[str, object]]:
        rows = self._connection.execute(
            "SELECT payload FROM candidates WHERE run_id = ? ORDER BY attempt_number",
            (run_id,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def artifact_manifest(self, run_id: str) -> list[dict[str, object]]:
        rows = self._connection.execute(
            "SELECT name, sha256, size_bytes, written_at FROM artifacts "
            "WHERE run_id = ? ORDER BY name",
            (run_id,),
        ).fetchall()
        return [
            {
                "name": row[0],
                "sha256": row[1],
                "size_bytes": row[2],
                "written_at": row[3],
            }
            for row in rows
        ]
