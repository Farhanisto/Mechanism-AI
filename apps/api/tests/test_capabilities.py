"""Tests for the capability registry and the capability router."""

import pytest
from app.capabilities.registry import (
    CapabilityEntry,
    CapabilityRegistry,
    default_registry,
)
from app.capabilities.router import detected_demand_categories, route_request
from app.mechanism.schemas import (
    CapabilitySupport,
    HardConstraints,
    NormalizedBrief,
    TargetMotion,
)


def make_brief(**evaluator_config: float) -> NormalizedBrief:
    return NormalizedBrief(
        target_motion=TargetMotion(travel_distance=100.0, trajectory_tolerance=5.0),
        constraints=HardConstraints(max_footprint=200.0),
        evaluator_config=dict(evaluator_config),
    )


def test_default_registry_contains_the_tested_four_bar_capability() -> None:
    registry = default_registry()
    entry = registry.get("four_bar_linkage")

    assert entry is not None
    assert entry.test_status == "tested"
    assert "travel_distance" in entry.evaluation_checks
    assert entry.known_limitations
    assert entry.parameter_constraints


def test_registry_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        CapabilityEntry(
            capability_id="x",
            version="1",
            domain="d",
            input_schema="i",
            output_schema="o",
            units="mm",
            surprise=True,
        )


def test_untested_capabilities_are_never_selected() -> None:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityEntry(
            capability_id="gear_train",
            version="0.0.1",
            domain="gears",
            input_schema="NormalizedBrief",
            output_schema="Candidate",
            units="mm",
            test_status="untested",
            domain_terms=("gear", "gearbox"),
        )
    )

    assessment = route_request(
        "Design a gear gearbox.",
        make_brief(),
        clarification_answers={},
        registry=registry,
    )

    assert assessment.status is CapabilitySupport.NOT_SUPPORTED
    assert any("not validated" in item for item in assessment.unsupported_requirements)


def test_linkage_prompt_routes_to_supported() -> None:
    assessment = route_request(
        "Design a compact four-bar linkage with 100 mm of travel.",
        make_brief(),
        clarification_answers={},
    )

    assert assessment.capability_id == "four_bar_linkage"
    assert assessment.status is CapabilitySupport.SUPPORTED
    assert assessment.unavailable_checks == []
    assert assessment.unsupported_requirements == []


def test_unmodeled_requirements_route_to_partial() -> None:
    prompt = "Design a four-bar linkage with 100 mm of travel that can carry a heavy load."

    unwaived = route_request(prompt, make_brief(), clarification_answers={})
    assert unwaived.status is CapabilitySupport.PARTIAL
    assert unwaived.unavailable_checks == ["structural_strength"]

    waived = route_request(
        prompt,
        make_brief(),
        clarification_answers={"verification_scope": "yes"},
    )
    assert waived.status is CapabilitySupport.PARTIAL
    assert waived.unavailable_checks == []
    assert any("structural_strength" in item for item in waived.unsupported_requirements)


def test_requested_checks_beyond_the_registry_block_support() -> None:
    assessment = route_request(
        "Design a four-bar linkage with 100 mm of travel.",
        make_brief(fatigue_cycles=1_000_000),
        clarification_answers={},
    )

    assert assessment.status is CapabilitySupport.PARTIAL
    assert assessment.unavailable_checks == ["fatigue_cycles"]


def test_non_mechanical_prompt_is_not_supported() -> None:
    assessment = route_request(
        "Design an attachable umbrella for a motorbike that deploys at the press of a button.",
        make_brief(),
        clarification_answers={},
    )

    assert assessment.status is CapabilitySupport.NOT_SUPPORTED
    assert assessment.capability_id == "none"
    assert assessment.unsupported_requirements


def test_detected_demand_categories() -> None:
    assert detected_demand_categories("carry a load at high temperature") == [
        "structural_strength",
        "thermal",
    ]
    assert detected_demand_categories("100 mm of travel") == []
