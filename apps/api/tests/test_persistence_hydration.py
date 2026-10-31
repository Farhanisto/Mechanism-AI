"""Run metadata survives an API restart when a volume is mounted."""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.mechanism.schemas import (
    Candidate,
    CandidateMetrics,
    CandidateRecord,
    DesignRun,
    Evaluation,
    EvaluationStatus,
    FourBarParameters,
    InputMotion,
    RunStatus,
    Stage,
)
from app.orchestration.design_run import RunStore
from app.persistence.artifacts import ArtifactStore
from app.persistence.metadata import MetadataStore


def _run() -> DesignRun:
    now = datetime.now(UTC)
    return DesignRun(
        run_id="run_hydration",
        status=RunStatus.COMPLETED,
        stage=Stage.COMPLETED,
        original_prompt="Design a compact four-bar linkage",
        created_at=now,
        updated_at=now,
        max_candidates=1,
    )


def _candidate_record() -> CandidateRecord:
    now = datetime.now(UTC)
    return CandidateRecord(
        candidate=Candidate(
            candidate_id="candidate_001",
            parameters=FourBarParameters(
                ground_length=120,
                crank_length=40,
                coupler_length=100,
                rocker_length=90,
            ),
            input_motion=InputMotion(start_angle_deg=0, end_angle_deg=360),
            generated_at=now,
            attempt_number=1,
            geometry_artifact_id="geometry_candidate_001.stl",
        ),
        evaluation=Evaluation(
            candidate_id="candidate_001",
            status=EvaluationStatus.PASSED,
            metrics=CandidateMetrics(
                travel_distance_mm=96.2,
                footprint_mm=130.0,
                trajectory_error_mm=0.4,
                cycle_completed=True,
                collision_free=True,
                simulation_valid=True,
            ),
            evaluator_version="0.1.0",
        ),
    )


def test_hydration_restores_runs_candidates_and_manifest(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    metadata = MetadataStore(artifact_root / "metadata.sqlite3")
    artifacts = ArtifactStore(artifact_root, metadata=metadata)
    store = RunStore(artifacts, metadata=metadata)

    run = store.create(_run())
    store.add_candidate(run.run_id, _candidate_record())
    artifacts.write_json(run.run_id, "note.json", {"ok": True})
    metadata.close()

    restarted_metadata = MetadataStore(artifact_root / "metadata.sqlite3")
    restarted_artifacts = ArtifactStore(artifact_root, metadata=restarted_metadata)
    restarted_artifacts.hydrate()
    restarted_store = RunStore(restarted_artifacts, metadata=restarted_metadata)
    restarted_store.hydrate()

    restored = restarted_store.get(run.run_id)
    assert restored is not None
    assert restored.status == RunStatus.COMPLETED
    assert restored.original_prompt == run.original_prompt
    restored_candidates = restarted_store.list_candidates(run.run_id)
    assert [record.candidate.candidate_id for record in restored_candidates] == [
        "candidate_001"
    ]
    manifest_names = {entry.name for entry in restarted_artifacts.manifest(run.run_id)}
    assert {"run.json", "candidates.json", "note.json"} <= manifest_names
    assert restarted_artifacts.read_json(run.run_id, "note.json") == {"ok": True}

    restarted_store.hydrate()
    assert len(restarted_store.list_candidates(run.run_id)) == 1
    restarted_metadata.close()


def test_hydration_skips_records_from_older_schemas(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    metadata = MetadataStore(artifact_root / "metadata.sqlite3")
    artifacts = ArtifactStore(artifact_root, metadata=metadata)
    store = RunStore(artifacts, metadata=metadata)

    run = store.create(_run())
    legacy = _candidate_record().model_dump(mode="json")
    legacy["evaluation"]["model_review"] = {"model": "retired-reviewer"}
    metadata._connection.execute(
        "INSERT OR REPLACE INTO candidates (run_id, candidate_id, attempt_number, payload) "
        "VALUES (?, ?, ?, ?)",
        (run.run_id, legacy["candidate"]["candidate_id"], 1, json.dumps(legacy)),
    )
    metadata._connection.commit()
    metadata.close()

    restarted_metadata = MetadataStore(artifact_root / "metadata.sqlite3")
    restarted_artifacts = ArtifactStore(artifact_root, metadata=restarted_metadata)
    restarted_store = RunStore(restarted_artifacts, metadata=restarted_metadata)
    restarted_store.hydrate()

    assert restarted_store.get(run.run_id) is not None
    assert restarted_store.list_candidates(run.run_id) == []
    restarted_metadata.close()


def test_hydration_without_metadata_is_a_noop(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path / "artifacts")
    store = RunStore(artifacts)
    artifacts.hydrate()
    store.hydrate()
    assert store.get("missing") is None
