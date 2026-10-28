"""Simulation engine selection for the design pipeline.

``auto`` runs the MuJoCo closed-loop engine when the optional ``sim``
dependencies are installed and falls back to the deterministic reference
solver otherwise. Every result is labelled with the engine that produced it.
When MuJoCo runs a valid simulation, the same candidate is also replayed with
the reference solver and the output-point deviation is recorded against the
documented tolerance.
"""

from app.mechanism.kinematics import DEFAULT_SAMPLE_COUNT, KinematicsError
from app.mechanism.schemas import Candidate, ReferenceComparison, SimulationResult
from app.simulation.mujoco_runner import (
    SimulationNotAvailable,
    is_mujoco_available,
    run_mujoco_simulation,
)
from app.simulation.reference_runner import run_reference_simulation
from app.simulation.trajectory import (
    DEFAULT_REFERENCE_TOLERANCE_MM,
    compare_trajectories,
    trajectory_from_simulation,
)

ENGINE_AUTO = "auto"
ENGINE_REFERENCE = "reference"
ENGINE_MUJOCO = "mujoco"
_ENGINES = (ENGINE_AUTO, ENGINE_REFERENCE, ENGINE_MUJOCO)


def run_candidate_simulation(
    candidate: Candidate,
    *,
    engine: str = ENGINE_AUTO,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
) -> SimulationResult:
    """Simulate a candidate with the selected engine and label the result."""
    if engine not in _ENGINES:
        raise ValueError(f"unknown simulation engine {engine!r}")
    if sample_count < 2:
        raise KinematicsError("sample_count must be at least 2")

    use_mujoco = engine == ENGINE_MUJOCO or (
        engine == ENGINE_AUTO and is_mujoco_available()
    )
    if not use_mujoco:
        return run_reference_simulation(candidate, sample_count=sample_count)

    result = run_mujoco_simulation(candidate, sample_count=sample_count)
    if result.simulation_valid and result.samples:
        result = _attach_reference_comparison(candidate, result, sample_count)
    return result


def _attach_reference_comparison(
    candidate: Candidate, result: SimulationResult, sample_count: int
) -> SimulationResult:
    reference = run_reference_simulation(candidate, sample_count=sample_count)
    if not reference.simulation_valid or len(reference.samples) != len(result.samples):
        return result
    comparison = compare_trajectories(
        trajectory_from_simulation(reference),
        trajectory_from_simulation(result),
        tolerance_mm=DEFAULT_REFERENCE_TOLERANCE_MM,
    )
    diagnostics = result.diagnostics
    reference_comparison = ReferenceComparison(
        reference_engine=reference.engine,
        reference_engine_version=reference.engine_version,
        sample_count=comparison.sample_count,
        tolerance_mm=comparison.tolerance_mm,
        max_deviation_mm=comparison.max_deviation_mm,
        mean_deviation_mm=comparison.mean_deviation_mm,
        within_tolerance=comparison.within_tolerance,
    )
    if diagnostics is None:
        return result
    return result.model_copy(
        update={
            "diagnostics": diagnostics.model_copy(
                update={"reference_comparison": reference_comparison}
            )
        }
    )


__all__ = [
    "ENGINE_AUTO",
    "ENGINE_MUJOCO",
    "ENGINE_REFERENCE",
    "SimulationNotAvailable",
    "run_candidate_simulation",
]
