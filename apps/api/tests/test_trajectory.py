import numpy as np
import pytest
from app.mechanism.schemas import (
    Point2D,
    SimulationResult,
    TraceSample,
)
from app.simulation.trajectory import (
    ComparisonResult,
    Trajectory,
    compare_trajectories,
    trajectory_from_simulation,
)


def make_trajectory(points: list[tuple[float, float]]) -> Trajectory:
    count = len(points)
    return Trajectory(
        time_s=np.linspace(0.0, 1.0, count),
        output_points_mm=np.asarray(points, dtype=float).reshape(-1, 2),
    )


def test_identical_trajectories_have_zero_deviation() -> None:
    reference = make_trajectory([(0.0, 0.0), (10.0, 5.0), (20.0, 0.0)])

    comparison = compare_trajectories(reference, reference)

    assert comparison == ComparisonResult(
        sample_count=3,
        max_deviation_mm=0.0,
        mean_deviation_mm=0.0,
        tolerance_mm=0.05,
        within_tolerance=True,
    )


def test_constant_offset_deviation_is_measured() -> None:
    reference = make_trajectory([(0.0, 0.0), (10.0, 0.0)])
    other = make_trajectory([(1.0, 0.0), (11.0, 0.0)])

    comparison = compare_trajectories(reference, other, tolerance_mm=0.5)

    assert comparison.max_deviation_mm == pytest.approx(1.0)
    assert comparison.mean_deviation_mm == pytest.approx(1.0)
    assert comparison.within_tolerance is False


def test_compare_rejects_mismatched_lengths() -> None:
    reference = make_trajectory([(0.0, 0.0), (1.0, 0.0)])
    other = make_trajectory([(0.0, 0.0)])

    with pytest.raises(ValueError, match="same number of samples"):
        compare_trajectories(reference, other)


def test_compare_rejects_empty_trajectories() -> None:
    empty = make_trajectory([])

    with pytest.raises(ValueError, match="must not be empty"):
        compare_trajectories(empty, empty)


def test_trajectory_from_simulation_extracts_output_points() -> None:
    sample = TraceSample(
        time_s=0.0,
        input_angle_deg=0.0,
        ground_pivot_a=Point2D(x=0.0, y=0.0),
        ground_pivot_b=Point2D(x=95.0, y=0.0),
        crank_pin=Point2D(x=35.0, y=0.0),
        rocker_pin=Point2D(x=130.0, y=60.0),
        output_point=Point2D(x=130.0, y=60.0),
    )
    result = SimulationResult(
        candidate_id="candidate_001",
        engine="reference_kinematics",
        engine_version="0.1.0",
        samples=[sample],
    )

    trajectory = trajectory_from_simulation(result)

    assert trajectory.output_points_mm.tolist() == [[130.0, 60.0]]
    assert trajectory.time_s.tolist() == [0.0]
