from app.mechanism.schemas import Candidate


class CompilerNotImplemented(RuntimeError):
    pass


def compile_candidate(candidate: Candidate) -> str:
    """Compile validated parameters into a deterministic MuJoCo MJCF document."""
    raise CompilerNotImplemented(
        "The deterministic MJCF compiler arrives in Milestone 2 together with the "
        "closed-loop MuJoCo feasibility spike."
    )
