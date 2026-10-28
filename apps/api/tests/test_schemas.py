import pytest
from app.ai.candidate_parser import parse_candidate
from app.mechanism.schemas import (
    DesignRunCreateRequest,
    FourBarParameters,
    NormalizedBrief,
)
from pydantic import ValidationError


def make_brief_payload() -> dict:
    return {
        "mechanism_type": "four_bar_linkage",
        "units": "mm",
        "target_motion": {
            "type": "near_horizontal",
            "travel_distance": 100,
            "trajectory_tolerance": 5,
        },
        "constraints": {
            "max_footprint": 200,
            "complete_motion_cycle": True,
            "avoid_collisions": True,
        },
    }


def test_normalized_brief_parses_prd_example() -> None:
    brief = NormalizedBrief.model_validate(make_brief_payload())

    assert brief.target_motion.travel_distance == 100
    assert brief.constraints.max_footprint == 200
    assert brief.assumptions == []


def test_normalized_brief_rejects_unknown_fields() -> None:
    payload = make_brief_payload()
    payload["unexpected"] = "field"

    with pytest.raises(ValidationError):
        NormalizedBrief.model_validate(payload)


def test_four_bar_parameters_require_positive_lengths() -> None:
    with pytest.raises(ValidationError):
        FourBarParameters(
            ground_length=100,
            crank_length=0,
            coupler_length=110,
            rocker_length=85,
        )


def test_parse_candidate_builds_typed_candidate() -> None:
    candidate = parse_candidate(
        {
            "mechanism_type": "four_bar_linkage",
            "parameters": {
                "ground_length": 100,
                "crank_length": 35,
                "coupler_length": 110,
                "rocker_length": 85,
            },
            "input_motion": {"start_angle_deg": 0, "end_angle_deg": 360},
        },
        candidate_id="candidate_001",
        attempt_number=1,
    )

    assert candidate.candidate_id == "candidate_001"
    assert candidate.parameters.coupler_length == 110
    assert candidate.input_motion.end_angle_deg == 360


def test_parse_candidate_rejects_extra_model_fields() -> None:
    with pytest.raises(ValidationError):
        parse_candidate(
            {
                "mechanism_type": "four_bar_linkage",
                "parameters": {
                    "ground_length": 100,
                    "crank_length": 35,
                    "coupler_length": 110,
                    "rocker_length": 85,
                    "generated_python": "import os",
                },
                "input_motion": {"start_angle_deg": 0, "end_angle_deg": 360},
            },
            candidate_id="candidate_001",
            attempt_number=1,
        )


def test_design_run_request_caps_candidate_budget() -> None:
    with pytest.raises(ValidationError):
        DesignRunCreateRequest(prompt="Design a linkage", options={"max_candidates": 4})

    request = DesignRunCreateRequest(prompt="Design a linkage")
    assert request.options.max_candidates == 3
