from typing import Any

import pytest
from app.ai.candidate_parser import (
    default_candidate,
    generate_candidate,
    parse_candidate,
)
from app.ai.meta_client import ModelCompletion
from app.ai.requirements_parser import default_brief_from_prompt, parse_requirements
from app.mechanism.schemas import (
    CandidateMetrics,
    Evaluation,
    EvaluationStatus,
)
from pydantic import ValidationError

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
    "assumptions": ["The output moves approximately horizontally."],
}

CANDIDATE_PAYLOAD: dict[str, Any] = {
    "mechanism_type": "four_bar_linkage",
    "parameters": {
        "ground_length": 95.0,
        "crank_length": 35.0,
        "coupler_length": 135.0,
        "rocker_length": 100.0,
    },
    "input_motion": {"start_angle_deg": 0.0, "end_angle_deg": 360.0},
}

PROMPT = (
    "Design a compact four-bar linkage that produces approximately 100 mm of "
    "near-horizontal movement and fits within a 200 mm footprint."
)


class FakeMetaClient:
    def __init__(self, payload: dict[str, Any], model: str = "muse-spark-1.3") -> None:
        self.payload = payload
        self.model = model
        self.calls: list[dict[str, Any]] = []

    @property
    def is_configured(self) -> bool:
        return True

    async def complete_json(self, **kwargs: Any) -> ModelCompletion:
        self.calls.append(kwargs)
        return ModelCompletion(
            payload=self.payload,
            model=self.model,
            latency_ms=12.5,
            usage={"total_tokens": 20},
        )

    async def aclose(self) -> None:
        return None


async def test_requirements_parser_validates_and_adds_standard_assumptions() -> None:
    client = FakeMetaClient(BRIEF_PAYLOAD)

    brief, completion = await parse_requirements(PROMPT, client=client)

    assert brief.target_motion.travel_distance == 100.0
    assert brief.constraints.max_footprint == 200.0
    assert any("rocker pin" in item for item in brief.assumptions)
    assert completion.model == "muse-spark-1.3"
    call = client.calls[0]
    assert call["schema_name"] == "normalized_brief"
    assert call["schema"]["additionalProperties"] is False
    assert set(call["schema"]["required"]) == {
        "mechanism_type",
        "units",
        "target_motion",
        "constraints",
        "assumptions",
    }
    assert "TargetMotionProposal" in call["schema"]["$defs"]


def test_default_brief_extracts_explicit_numbers() -> None:
    brief = default_brief_from_prompt(PROMPT)

    assert brief.target_motion.travel_distance == 100.0
    assert brief.constraints.max_footprint == 200.0
    assert brief.target_motion.trajectory_tolerance == 5.0
    assert any("Near-horizontal" in item for item in brief.assumptions)
    assert any("rocker pin" in item for item in brief.assumptions)


def test_default_brief_records_defaults_for_missing_values() -> None:
    brief = default_brief_from_prompt("Design a four-bar linkage.")

    assert brief.target_motion.travel_distance == 100.0
    assert brief.constraints.max_footprint == 200.0
    assert any("Travel distance defaulted" in item for item in brief.assumptions)
    assert any("Maximum footprint defaulted" in item for item in brief.assumptions)


async def test_candidate_generation_parses_typed_candidate() -> None:
    client = FakeMetaClient(CANDIDATE_PAYLOAD)
    brief = default_brief_from_prompt(PROMPT)

    candidate, completion = await generate_candidate(
        brief,
        client=client,
        attempt_number=2,
    )

    assert candidate.candidate_id == "candidate_002"
    assert candidate.attempt_number == 2
    assert candidate.parameters.coupler_length == 135.0
    assert completion.usage["total_tokens"] == 20
    call = client.calls[0]
    assert call["schema_name"] == "four_bar_candidate"
    assert "candidate attempt 2" in call["user_prompt"]


async def test_repair_prompt_includes_previous_evaluation() -> None:
    client = FakeMetaClient(CANDIDATE_PAYLOAD)
    brief = default_brief_from_prompt(PROMPT)
    previous = default_candidate(attempt_number=1)
    evaluation = Evaluation(
        candidate_id=previous.candidate_id,
        status=EvaluationStatus.FAILED,
        metrics=CandidateMetrics(
            travel_distance_mm=72.0,
            footprint_mm=180.0,
            trajectory_error_mm=12.0,
            cycle_completed=True,
            collision_free=True,
            simulation_valid=True,
        ),
        failed_constraints=["travel_distance", "trajectory_tolerance"],
        evaluator_version="test",
        diagnostic_notes=["Travel distance is too short."],
    )

    await generate_candidate(
        brief,
        client=client,
        attempt_number=2,
        previous_candidate=previous,
        previous_evaluation=evaluation,
    )

    prompt = client.calls[0]["user_prompt"]
    assert "travel_distance" in prompt
    assert "Travel distance is too short." in prompt
    assert "Propose a revised candidate" in prompt


def test_candidate_parser_rejects_extra_fields() -> None:
    payload = {**CANDIDATE_PAYLOAD, "unexpected": True}

    with pytest.raises(ValidationError):
        parse_candidate(payload, candidate_id="candidate_001", attempt_number=1)


def test_default_candidates_change_with_attempt() -> None:
    first = default_candidate(attempt_number=1)
    second = default_candidate(attempt_number=2)

    assert first.parameters != second.parameters
    assert second.candidate_id == "candidate_002"
