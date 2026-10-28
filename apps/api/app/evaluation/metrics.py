from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from app.mechanism.schemas import CandidateMetrics, SimulationResult

PointArray = NDArray[np.float64]


def as_points(points: Sequence[Sequence[float]] | PointArray) -> PointArray:
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] != 2 or array.shape[0] == 0:
        raise ValueError("points must be a non-empty array with shape (n, 2)")
    return array


def travel_distance(points: Sequence[Sequence[float]] | PointArray) -> float:
    """Maximum pairwise output-point displacement, in the input units."""
    array = as_points(points)
    deltas = array[:, None, :] - array[None, :, :]
    return float(np.max(np.linalg.norm(deltas, axis=-1)))


def bounding_box(
    points: Sequence[Sequence[float]] | PointArray,
) -> tuple[float, float, float, float]:
    array = as_points(points)
    return (
        float(np.min(array[:, 0])),
        float(np.min(array[:, 1])),
        float(np.max(array[:, 0])),
        float(np.max(array[:, 1])),
    )


def footprint(points: Sequence[Sequence[float]] | PointArray) -> float:
    """Largest bounding-box dimension of the mechanism geometry."""
    min_x, min_y, max_x, max_y = bounding_box(points)
    return max(max_x - min_x, max_y - min_y)


def horizontal_deviation(points: Sequence[Sequence[float]] | PointArray) -> float:
    """Mean absolute vertical deviation from the path's mean Y coordinate.

    This is the MVP interpretation of a near-horizontal target: it rewards a
    straight, level output path without claiming a specific target polyline.
    """
    array = as_points(points)
    mean_y = float(np.mean(array[:, 1]))
    return float(np.mean(np.abs(array[:, 1] - mean_y)))


def measure_simulation(result: SimulationResult) -> CandidateMetrics:
    """Convert a reference trace into evaluator-owned metrics."""
    if not result.simulation_valid or not result.samples:
        return CandidateMetrics(
            travel_distance_mm=0.0,
            footprint_mm=0.0,
            trajectory_error_mm=0.0,
            cycle_completed=False,
            collision_free=False,
            simulation_valid=False,
        )

    output_points = [
        (sample.output_point.x, sample.output_point.y) for sample in result.samples
    ]
    joint_points: list[tuple[float, float]] = []
    for sample in result.samples:
        joint_points.extend(
            [
                (sample.ground_pivot_a.x, sample.ground_pivot_a.y),
                (sample.ground_pivot_b.x, sample.ground_pivot_b.y),
                (sample.crank_pin.x, sample.crank_pin.y),
                (sample.rocker_pin.x, sample.rocker_pin.y),
            ]
        )

    return CandidateMetrics(
        travel_distance_mm=travel_distance(output_points),
        footprint_mm=footprint(joint_points),
        trajectory_error_mm=horizontal_deviation(output_points),
        cycle_completed=result.cycle_completed,
        collision_free=result.collision_free,
        simulation_valid=result.simulation_valid,
    )


def trajectory_deviation(
    points: Sequence[Sequence[float]] | PointArray,
    target_path: Sequence[Sequence[float]] | PointArray,
) -> float:
    """Mean distance from sampled output points to the target polyline."""
    samples = as_points(points)
    path = as_points(target_path)
    if path.shape[0] < 2:
        raise ValueError("target_path requires at least two points")

    best = np.full(samples.shape[0], np.inf)
    for start, end in zip(path[:-1], path[1:], strict=True):
        segment = end - start
        length_sq = float(np.dot(segment, segment))
        if length_sq == 0.0:
            distances = np.linalg.norm(samples - start, axis=1)
        else:
            offsets = samples - start
            t = np.clip((offsets @ segment) / length_sq, 0.0, 1.0)
            projections = start + t[:, None] * segment
            distances = np.linalg.norm(samples - projections, axis=1)
        best = np.minimum(best, distances)

    return float(np.mean(best))
