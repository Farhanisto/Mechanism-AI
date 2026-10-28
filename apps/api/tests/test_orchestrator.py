from pathlib import Path
from typing import Any

from app.ai.meta_client import (
    MetaModelRequestError,
    ModelCompletion,
)
from app.mechanism.schemas import DesignRunCreateRequest
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
    ) -> None:
        self.candidate_payloads = candidate_payloads
        self.error = error
        self.schema_names: list[str] = []

    @property
    def is_configured(self) -> bool:
        return True

    async def complete_json(self, **kwargs: Any) -> ModelCompletion:
        if self.error is not None:
            raise self.error
        schema_name = kwargs["schema_name"]
        self.schema_names.append(schema_name)
        if schema_name == "normalized_brief":
            payload = BRIEF_PAYLOAD
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
) -> tuple[DesignRunOrchestrator, EventBroker]:
    artifacts = ArtifactStore(tmp_path)
    store = RunStore(artifacts)
    events = EventBroker()
    orchestrator = DesignRunOrchestrator(
        store=store,
        events=events,
        artifacts=artifacts,
        meta_client=client,
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
    assert "requirements_parsed" in event_names
    assert "repair_started" in event_names
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
