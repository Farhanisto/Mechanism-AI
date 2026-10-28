"""Reference kinematic simulation used until the MuJoCo runner is integrated."""

from app.mechanism.kinematics import (
    DEFAULT_SAMPLE_COUNT,
    ENGINE_NAME,
    ENGINE_VERSION,
    KinematicsError,
    simulate_four_bar,
)
from app.mechanism.schemas import Candidate, SimulationResult

__all__ = [
    "DEFAULT_SAMPLE_COUNT",
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "KinematicsError",
    "run_reference_simulation",
]


def run_reference_simulation(
    candidate: Candidate,
    *,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
) -> SimulationResult:
    """Run the deterministic reference solver and label the engine honestly."""
    return simulate_four_bar(
        candidate,
        sample_count=sample_count,
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
    )
