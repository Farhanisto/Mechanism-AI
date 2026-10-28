from dataclasses import dataclass

from app.mechanism.schemas import Candidate


class SimulationNotAvailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SimulationResult:
    candidate_id: str
    steps: int
    time_s: list[float]
    output_points_mm: list[tuple[float, float]]


def run_simulation(candidate: Candidate, model_xml: str) -> SimulationResult:
    """Run a compiled candidate and record bounded-interval state samples."""
    raise SimulationNotAvailable(
        "MuJoCo closed-loop integration arrives in Milestone 2. Install the optional "
        "dependencies with `uv sync --extra sim` once the feasibility spike is ready."
    )
