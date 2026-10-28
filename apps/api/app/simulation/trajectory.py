from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.mechanism.schemas import SimulationResult

DEFAULT_REFERENCE_TOLERANCE_MM = 0.05


@dataclass(frozen=True)
class Trajectory:
    time_s: NDArray[np.float64]
    output_points_mm: NDArray[np.float64]

    def __post_init__(self) -> None:
        if self.time_s.ndim != 1:
            raise ValueError("time_s must be one-dimensional")
        if self.output_points_mm.shape != (self.time_s.shape[0], 2):
            raise ValueError("output_points_mm must have shape (len(time_s), 2)")


@dataclass(frozen=True)
class ComparisonResult:
    sample_count: int
    max_deviation_mm: float
    mean_deviation_mm: float
    tolerance_mm: float
    within_tolerance: bool


def trajectory_from_simulation(result: SimulationResult) -> Trajectory:
    """Extract the sampled output-point trajectory from a simulation result."""
    return Trajectory(
        time_s=np.asarray([sample.time_s for sample in result.samples], dtype=float),
        output_points_mm=np.asarray(
            [[sample.output_point.x, sample.output_point.y] for sample in result.samples],
            dtype=float,
        ),
    )


def compare_trajectories(
    reference: Trajectory,
    other: Trajectory,
    *,
    tolerance_mm: float = DEFAULT_REFERENCE_TOLERANCE_MM,
) -> ComparisonResult:
    """Compare two index-aligned traces sampled at the same normalized times.

    The deviation is the Euclidean distance between output points at matching
    samples. Traces must cover the same samples; a mismatch in length raises
    rather than silently comparing different motions.
    """
    if reference.output_points_mm.shape != other.output_points_mm.shape:
        raise ValueError("trajectories must have the same number of samples")
    if reference.output_points_mm.shape[0] == 0:
        raise ValueError("trajectories must not be empty")
    deviations = np.linalg.norm(
        reference.output_points_mm - other.output_points_mm, axis=1
    )
    max_deviation = float(np.max(deviations))
    return ComparisonResult(
        sample_count=int(deviations.shape[0]),
        max_deviation_mm=max_deviation,
        mean_deviation_mm=float(np.mean(deviations)),
        tolerance_mm=tolerance_mm,
        within_tolerance=max_deviation <= tolerance_mm,
    )
