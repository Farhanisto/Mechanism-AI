import pytest
from app.evaluation.metrics import (
    as_points,
    bounding_box,
    footprint,
    horizontal_deviation,
    trajectory_deviation,
    travel_distance,
)


def test_travel_distance_measures_max_displacement() -> None:
    points = [(0.0, 0.0), (3.0, 4.0), (1.0, 0.0)]

    assert travel_distance(points) == pytest.approx(5.0)


def test_footprint_uses_largest_bounding_dimension() -> None:
    points = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)]

    assert bounding_box(points) == (0.0, 0.0, 10.0, 4.0)
    assert footprint(points) == pytest.approx(10.0)


def test_trajectory_deviation_is_zero_on_target_path() -> None:
    target = [(0.0, 0.0), (100.0, 0.0)]
    samples = [(25.0, 0.0), (50.0, 0.0), (75.0, 0.0)]

    assert trajectory_deviation(samples, target) == pytest.approx(0.0)


def test_trajectory_deviation_averages_offsets() -> None:
    target = [(0.0, 0.0), (100.0, 0.0)]
    samples = [(20.0, 2.0), (80.0, -2.0)]

    assert trajectory_deviation(samples, target) == pytest.approx(2.0)


def test_horizontal_deviation_measures_straightness() -> None:
    level = [(0.0, 10.0), (25.0, 10.0), (100.0, 10.0)]
    offset = [(0.0, 8.0), (25.0, 10.0), (100.0, 12.0)]

    assert horizontal_deviation(level) == pytest.approx(0.0)
    assert horizontal_deviation(offset) == pytest.approx(4.0 / 3.0)


def test_as_points_rejects_malformed_input() -> None:
    with pytest.raises(ValueError):
        as_points([])
    with pytest.raises(ValueError):
        as_points([(0.0, 1.0, 2.0)])
