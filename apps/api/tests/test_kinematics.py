from datetime import UTC, datetime

import pytest
from app.evaluation.geometry_checks import has_moving_link_collision, segments_intersect
from app.evaluation.metrics import measure_simulation
from app.mechanism.kinematics import KinematicsError, simulate_four_bar
from app.mechanism.schemas import (
    Candidate,
    FourBarParameters,
    InputMotion,
    Point2D,
    TraceSample,
)


def make_candidate(
    *,
    ground: float = 95.0,
    crank: float = 35.0,
    coupler: float = 135.0,
    rocker: float = 100.0,
    start: float = 0.0,
    end: float = 360.0,
    candidate_id: str = "candidate_001",
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
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


def test_reference_geometry_meets_demo_targets() -> None:
    result = simulate_four_bar(make_candidate())

    metrics = measure_simulation(result)

    assert result.simulation_valid is True
    assert result.cycle_completed is True
    assert result.collision_free is True
    assert len(result.samples) == 361
    assert metrics.travel_distance_mm == pytest.approx(99.51, abs=0.01)
    assert metrics.footprint_mm == pytest.approx(181.97, abs=0.01)
    assert metrics.trajectory_error_mm == pytest.approx(4.14, abs=0.01)


def test_full_cycle_closes_on_the_same_branch() -> None:
    result = simulate_four_bar(make_candidate(), sample_count=73)

    first = result.samples[0]
    last = result.samples[-1]
    assert first.input_angle_deg == 0
    assert last.input_angle_deg == 360
    assert last.output_point.x == pytest.approx(first.output_point.x, abs=1e-6)
    assert last.output_point.y == pytest.approx(first.output_point.y, abs=1e-6)


def test_incomplete_input_range_is_valid_but_not_a_cycle() -> None:
    result = simulate_four_bar(make_candidate(start=0, end=180), sample_count=73)

    assert result.simulation_valid is True
    assert result.cycle_completed is False
    assert result.samples[-1].input_angle_deg == 180


def test_unclosable_linkage_reports_invalid_simulation() -> None:
    result = simulate_four_bar(
        make_candidate(ground=100, crank=10, coupler=20, rocker=20),
        sample_count=73,
    )

    assert result.simulation_valid is False
    assert result.cycle_completed is False
    assert result.collision_free is False
    assert result.failure_reason is not None
    assert result.samples == []


def test_solver_rejects_too_few_samples() -> None:
    with pytest.raises(KinematicsError):
        simulate_four_bar(make_candidate(), sample_count=1)


def test_segments_intersect_for_crossing_and_touching_segments() -> None:
    assert segments_intersect((0, 0), (2, 2), (0, 2), (2, 0)) is True
    assert segments_intersect((0, 0), (2, 2), (2, 2), (4, 2)) is True
    assert segments_intersect((0, 0), (1, 0), (0, 1), (1, 1)) is False
    assert segments_intersect((0, 0), (2, 0), (1, 0), (3, 0)) is True


def test_moving_link_collision_uses_crank_and_rocker() -> None:
    sample = TraceSample(
        time_s=0.0,
        input_angle_deg=0.0,
        ground_pivot_a=Point2D(x=0, y=0),
        ground_pivot_b=Point2D(x=100, y=0),
        crank_pin=Point2D(x=50, y=50),
        rocker_pin=Point2D(x=0, y=50),
        output_point=Point2D(x=0, y=50),
    )

    assert has_moving_link_collision([sample]) is True
