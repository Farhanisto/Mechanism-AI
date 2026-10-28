from datetime import UTC, datetime

import pytest
from app.ai.candidate_parser import default_candidate
from app.mechanism.schemas import (
    Candidate,
    FourBarParameters,
    InputMotion,
    MechanismType,
)
from app.simulation.mujoco_runner import (
    ENGINE_NAME,
    LOOP_CLOSURE_LIMIT_MM,
    run_mujoco_simulation,
)
from app.simulation.runner import run_candidate_simulation

mujoco = pytest.importorskip("mujoco")


def make_candidate(
    ground: float,
    crank: float,
    coupler: float,
    rocker: float,
    *,
    start: float = 0.0,
    end: float = 360.0,
) -> Candidate:
    return Candidate(
        candidate_id="candidate_001",
        mechanism_type=MechanismType.FOUR_BAR_LINKAGE,
        parameters=FourBarParameters(
            ground_length=ground,
            crank_length=crank,
            coupler_length=coupler,
            rocker_length=rocker,
        ),
        input_motion=InputMotion(start_angle_deg=start, end_angle_deg=end),
        generated_at=datetime.now(UTC),
        attempt_number=1,
    )


def test_runs_the_fallback_candidate() -> None:
    result = run_mujoco_simulation(default_candidate(attempt_number=1))

    assert result.simulation_valid is True
    assert result.failure_reason is None
    assert result.engine == ENGINE_NAME
    assert result.engine_version == mujoco.__version__
    assert len(result.samples) == 361
    assert result.cycle_completed is True
    assert result.collision_free is True
    assert result.diagnostics is not None
    assert result.diagnostics.compiler_version is not None
    assert result.diagnostics.max_loop_closure_error_mm <= LOOP_CLOSURE_LIMIT_MM
    assert result.diagnostics.contacts_enabled is False


def test_is_deterministic_across_runs() -> None:
    candidate = default_candidate(attempt_number=1)

    first = run_mujoco_simulation(candidate)
    second = run_mujoco_simulation(candidate)

    assert first == second


def test_matches_reference_within_documented_tolerance() -> None:
    for attempt in (1, 2, 3):
        result = run_candidate_simulation(
            default_candidate(attempt_number=attempt), engine="mujoco"
        )

        assert result.diagnostics is not None
        comparison = result.diagnostics.reference_comparison
        assert comparison is not None
        assert comparison.within_tolerance is True
        assert comparison.max_deviation_mm <= comparison.tolerance_mm
        assert comparison.sample_count == len(result.samples)


def test_unclosable_mid_cycle_fails_structured() -> None:
    result = run_mujoco_simulation(make_candidate(100.0, 60.0, 30.0, 25.0))

    assert result.simulation_valid is False
    assert result.failure_reason is not None
    assert "closure" in result.failure_reason


def test_invalid_candidate_fails_structured() -> None:
    result = run_mujoco_simulation(make_candidate(1000.0, 10.0, 10.0, 10.0))

    assert result.simulation_valid is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("invalid candidate")


def test_partial_span_is_valid_but_not_a_cycle() -> None:
    result = run_mujoco_simulation(make_candidate(95.0, 35.0, 135.0, 100.0, end=180.0))

    assert result.simulation_valid is True
    assert result.cycle_completed is False
    assert len(result.samples) == 361
