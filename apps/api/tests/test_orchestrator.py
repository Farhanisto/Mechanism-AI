import asyncio
import hashlib
from pathlib import Path
from typing import Any

from app.ai.meta_client import (
    MetaModelRequestError,
    ModelCompletion,
)
from app.evaluation.evaluator import evaluate_candidate
from app.mechanism.kinematics import KinematicsError
from app.mechanism.schemas import (
    DesignRunCreateRequest,
    EvidenceBundle,
    NormalizedBrief,
)
from app.orchestration.design_run import DesignRunOrchestrator, EventBroker, RunStore
from app.persistence.artifacts import ArtifactStore

PROMPT = "Design a four-bar linkage with 100 mm of travel in a 200 mm footprint."

BRIEF_PAYLOAD: dict[str, Any] = {
    "mechanism_type": "four_bar_linkage",
    "units": "mm",
    "target_motion": {
        "type": "near_horizontal",
        "travel_distance": 100.0,
        "trajectory_tolerance": 5.0,
    },
    "constraints": {
        "max_footprint": 200.0,
        "complete_motion_cycle": True,
        "avoid_collisions": True,
    },
    "assumptions": [],
}


def candidate_payload(
    ground: float,
    crank: float,
    coupler: float,
    rocker: float,
) -> dict[str, Any]:
    return {
        "mechanism_type": "four_bar_linkage",
        "parameters": {
            "ground_length": ground,
            "crank_length": crank,
            "coupler_length": coupler,
            "rocker_length": rocker,
        },
        "input_motion": {"start_angle_deg": 0.0, "end_angle_deg": 360.0},
    }


class ScriptedMetaClient:
    def __init__(
        self,
        *,
        candidate_payloads: list[dict[str, Any]],
        error: Exception | None = None,
        brief_payload: dict[str, Any] | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self.candidate_payloads = candidate_payloads
        self.error = error
        self.brief_payload = brief_payload
        self.delay_s = delay_s
        self.schema_names: list[str] = []

    @property
    def is_configured(self) -> bool:
        return True

    async def complete_json(self, **kwargs: Any) -> ModelCompletion:
        if self.delay_s > 0.0:
            await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        schema_name = kwargs["schema_name"]
        self.schema_names.append(schema_name)
        if schema_name == "normalized_brief":
            payload = self.brief_payload if self.brief_payload is not None else BRIEF_PAYLOAD
        else:
            payload = self.candidate_payloads.pop(0)
        return ModelCompletion(
            payload=payload,
            model="muse-spark-1.3",
            latency_ms=25.0,
            usage={"total_tokens": 30},
        )

    async def aclose(self) -> None:
        return None


def make_orchestrator(
    tmp_path: Path,
    client: ScriptedMetaClient,
    *,
    max_run_seconds: float = 60.0,
) -> tuple[DesignRunOrchestrator, EventBroker]:
    artifacts = ArtifactStore(tmp_path)
    store = RunStore(artifacts)
    events = EventBroker()
    orchestrator = DesignRunOrchestrator(
        store=store,
        events=events,
        artifacts=artifacts,
        meta_client=client,
        max_run_seconds=max_run_seconds,
    )
    return orchestrator, events


async def replay_events(broker: EventBroker, run_id: str) -> list[str]:
    return [event.event async for event in broker.stream(run_id) if event is not None]


async def test_ai_pipeline_repairs_a_failed_candidate(tmp_path: Path) -> None:
    client = ScriptedMetaClient(
        candidate_payloads=[
            candidate_payload(95, 35, 100, 80),
            candidate_payload(95, 35, 135, 100),
        ]
    )
    orchestrator, broker = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(
        DesignRunCreateRequest(prompt=PROMPT, options={"max_candidates": 3})
    )

    await orchestrator.execute(run.run_id)

    stored_run = orchestrator.store.get(run.run_id)
    candidates = orchestrator.store.list_candidates(run.run_id)
    assert stored_run is not None
    assert stored_run.status.value == "completed"
    assert stored_run.stage.value == "completed"
    assert stored_run.no_pass is False
    assert stored_run.final_candidate_id == "candidate_002"
    assert len(candidates) == 2
    assert candidates[0].evaluation is not None
    assert candidates[0].evaluation.status.value == "failed"
    assert "travel_distance" in candidates[0].evaluation.failed_constraints
    assert candidates[1].evaluation is not None
    assert candidates[1].evaluation.status.value == "passed"

    event_names = await replay_events(broker, run.run_id)
    assert "requirements_ready" in event_names
    assert "repair_started" in event_names
    assert "artifact_ready" in event_names
    assert event_names[-1] == "run_completed"
    assert "run_failed" not in event_names

    evidence = orchestrator.artifacts.read_json(run.run_id, "evidence.json")
    assert evidence["requirements"]["source"] == "meta_model"
    assert evidence["final_candidate_id"] == "candidate_002"
    assert evidence["no_pass"] is False
    assert len(evidence["provider_calls"]) == 3
    assert evidence["provider_calls"][0]["stage"] == "requirements"
    assert evidence["provider_calls"][1]["stage"] == "candidate_001"


async def test_ai_pipeline_marks_run_failed_on_model_error(tmp_path: Path) -> None:
    client = ScriptedMetaClient(
        candidate_payloads=[],
        error=MetaModelRequestError(
            "The Meta model request failed with HTTP 401.",
            status_code=401,
        ),
    )
    orchestrator, broker = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PROMPT))

    await orchestrator.execute(run.run_id)

    stored_run = orchestrator.store.get(run.run_id)
    assert stored_run is not None
    assert stored_run.status.value == "failed"
    assert stored_run.error_code == "MODEL_REQUEST_FAILED"
    assert orchestrator.store.list_candidates(run.run_id) == []

    event_names = await replay_events(broker, run.run_id)
    assert event_names[-1] == "run_failed"
    error_artifact = orchestrator.artifacts.read_json(run.run_id, "error.json")
    assert error_artifact["error_code"] == "MODEL_REQUEST_FAILED"


async def test_ai_pipeline_marks_run_failed_on_invalid_model_output(tmp_path: Path) -> None:
    client = ScriptedMetaClient(
        candidate_payloads=[],
        brief_payload={"mechanism_type": "four_bar_linkage"},
    )
    orchestrator, broker = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PROMPT))

    await orchestrator.execute(run.run_id)

    stored_run = orchestrator.store.get(run.run_id)
    assert stored_run is not None
    assert stored_run.status.value == "failed"
    assert stored_run.error_code == "INVALID_MODEL_OUTPUT"

    event_names = await replay_events(broker, run.run_id)
    assert event_names[-1] == "run_failed"


async def test_ai_pipeline_marks_run_failed_on_timeout(tmp_path: Path) -> None:
    client = ScriptedMetaClient(candidate_payloads=[], delay_s=0.2)
    orchestrator, broker = make_orchestrator(tmp_path, client, max_run_seconds=0.05)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PROMPT))

    await orchestrator.execute(run.run_id)

    stored_run = orchestrator.store.get(run.run_id)
    assert stored_run is not None
    assert stored_run.status.value == "failed"
    assert stored_run.error_code == "RUN_TIMEOUT"

    event_names = await replay_events(broker, run.run_id)
    assert event_names[-1] == "run_failed"


async def test_ai_pipeline_marks_run_failed_on_simulation_error(
    tmp_path: Path, monkeypatch
) -> None:
    def raise_kinematics_error(candidate: Any, **kwargs: Any) -> None:
        raise KinematicsError("the solver failed")

    monkeypatch.setattr(
        "app.orchestration.design_run.run_candidate_simulation",
        raise_kinematics_error,
    )
    client = ScriptedMetaClient(
        candidate_payloads=[candidate_payload(95, 35, 135, 100)]
    )
    orchestrator, broker = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PROMPT))

    await orchestrator.execute(run.run_id)

    stored_run = orchestrator.store.get(run.run_id)
    assert stored_run is not None
    assert stored_run.status.value == "failed"
    assert stored_run.error_code == "SIMULATION_ERROR"

    event_names = await replay_events(broker, run.run_id)
    assert event_names[-1] == "run_failed"


async def test_cancel_request_stops_the_pipeline(tmp_path: Path) -> None:
    client = ScriptedMetaClient(
        candidate_payloads=[candidate_payload(95, 35, 135, 100)], delay_s=0.25
    )
    orchestrator, broker = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PROMPT))
    orchestrator.request_cancel(run.run_id)

    await orchestrator.execute(run.run_id)

    stored_run = orchestrator.store.get(run.run_id)
    assert stored_run is not None
    assert stored_run.status.value == "cancelled"
    assert stored_run.stage.value == "cancelled"
    assert orchestrator.store.list_candidates(run.run_id) == []

    event_names = await replay_events(broker, run.run_id)
    assert event_names[-1] == "run_cancelled"
    assert "run_completed" not in event_names


async def test_event_order_matches_the_contract(tmp_path: Path) -> None:
    client = ScriptedMetaClient(candidate_payloads=[candidate_payload(95, 35, 135, 100)])
    orchestrator, broker = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PROMPT))

    await orchestrator.execute(run.run_id)

    event_names = await replay_events(broker, run.run_id)
    assert event_names == [
        "run_started",
        "requirements_ready",
        "candidate_generated",
        "simulation_completed",
        "evaluation_completed",
        "artifact_ready",
        "run_completed",
    ]


async def test_evidence_bundle_is_reconstructable(tmp_path: Path) -> None:
    client = ScriptedMetaClient(candidate_payloads=[candidate_payload(95, 35, 135, 100)])
    orchestrator, _ = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PROMPT))

    await orchestrator.execute(run.run_id)

    evidence = orchestrator.artifacts.read_json(run.run_id, "evidence.json")
    bundle = EvidenceBundle.model_validate(evidence)
    assert bundle.outcome == "passed"
    assert bundle.limitations

    for entry in bundle.manifest:
        raw = (tmp_path / run.run_id / entry.name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry.sha256
        assert len(raw) == entry.size_bytes

    record = bundle.candidates[-1]
    assert record.evaluation is not None
    brief = NormalizedBrief.model_validate(bundle.requirements["brief"])
    re_evaluated = evaluate_candidate(
        brief, record.evaluation.metrics, record.candidate.candidate_id
    )
    assert re_evaluated.status == record.evaluation.status
    assert re_evaluated.failed_constraints == record.evaluation.failed_constraints


async def test_completed_run_never_passes_with_unresolved_checks(tmp_path: Path) -> None:
    client = ScriptedMetaClient(candidate_payloads=[candidate_payload(100, 60, 30, 25)])
    orchestrator, _ = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(
        DesignRunCreateRequest(prompt=PROMPT, options={"max_candidates": 1})
    )

    await orchestrator.execute(run.run_id)

    stored_run = orchestrator.store.get(run.run_id)
    assert stored_run is not None
    assert stored_run.status.value == "completed"
    assert stored_run.no_pass is True
    record = orchestrator.store.list_candidates(run.run_id)[0]
    assert record.evaluation is not None
    assert record.evaluation.status.value == "failed"
    assert "simulation_integrity" in record.evaluation.failed_constraints
