from datetime import UTC, datetime
from pathlib import Path

from app.mechanism.schemas import (
    CandidateRecord,
    DesignRun,
    RunStatus,
    Stage,
)
from app.orchestration.design_run import RunStore
from app.persistence.artifacts import ArtifactStore
from app.persistence.metadata import MetadataStore


def make_record(candidate_id: str, attempt: int) -> CandidateRecord:
    return CandidateRecord.model_validate(
        {
            "candidate": {
                "candidate_id": candidate_id,
                "mechanism_type": "four_bar_linkage",
                "parameters": {
                    "ground_length": 95.0,
                    "crank_length": 35.0,
                    "coupler_length": 135.0,
                    "rocker_length": 100.0,
                },
                "input_motion": {"start_angle_deg": 0.0, "end_angle_deg": 360.0},
                "generated_at": datetime.now(UTC).isoformat(),
                "attempt_number": attempt,
            },
            "evaluation": None,
        }
    )


def test_metadata_store_mirrors_runs_candidates_and_artifacts(tmp_path: Path) -> None:
    metadata = MetadataStore(tmp_path / "metadata.sqlite3")
    artifacts = ArtifactStore(tmp_path / "artifacts", metadata=metadata)
    store = RunStore(artifacts, metadata=metadata)

    now = datetime.now(UTC)
    run = DesignRun(
        run_id="run_meta",
        status="running",
        stage="simulate",
        original_prompt="Design a four-bar linkage.",
        created_at=now,
        updated_at=now,
        max_candidates=3,
    )
    store.create(run)
    record = make_record("candidate_001", 1)
    store.add_candidate(run.run_id, record)
    artifacts.write_json(run.run_id, "brief.json", {"source": "deterministic_fallback"})

    stored_run = metadata.get_run(run.run_id)
    assert stored_run is not None
    assert stored_run["status"] == "running"
    assert stored_run["run_id"] == "run_meta"

    candidates = metadata.list_candidate_payloads(run.run_id)
    assert len(candidates) == 1
    assert candidates[0]["candidate"]["candidate_id"] == "candidate_001"

    manifest = metadata.artifact_manifest(run.run_id)
    names = {entry["name"] for entry in manifest}
    assert {"run.json", "candidates.json", "brief.json"} <= names
    brief_entry = next(entry for entry in manifest if entry["name"] == "brief.json")
    memory_entry = next(
        entry for entry in artifacts.manifest(run.run_id) if entry.name == "brief.json"
    )
    assert brief_entry["sha256"] == memory_entry.sha256

    metadata.close()


def test_metadata_records_updated_status(tmp_path: Path) -> None:
    metadata = MetadataStore(tmp_path / "metadata.sqlite3")
    store = RunStore(ArtifactStore(tmp_path / "artifacts", metadata=metadata), metadata=metadata)

    now = datetime.now(UTC)
    run = DesignRun(
        run_id="run_meta2",
        status="running",
        stage="report",
        original_prompt="Design a four-bar linkage.",
        created_at=now,
        updated_at=now,
    )
    store.create(run)
    run.status = RunStatus.COMPLETED
    run.stage = Stage.COMPLETED
    run.no_pass = True
    store.update(run)

    stored_run = metadata.get_run("run_meta2")
    assert stored_run is not None
    assert stored_run["status"] == "completed"
    assert stored_run["no_pass"] == 1

    metadata.close()
