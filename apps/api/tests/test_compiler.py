import math
from datetime import UTC, datetime

import pytest
from app.ai.candidate_parser import default_candidate
from app.mechanism.compiler import (
    COMPILER_VERSION,
    InvalidCandidateError,
    compile_candidate,
)
from app.mechanism.schemas import (
    Candidate,
    FourBarParameters,
    InputMotion,
    MechanismType,
)


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


def test_compile_is_deterministic_and_versioned() -> None:
    candidate = default_candidate(attempt_number=1)

    first = compile_candidate(candidate)
    second = compile_candidate(candidate)

    assert first == second
    assert first.compiler_version == COMPILER_VERSION
    assert COMPILER_VERSION in first.mjcf_xml


def test_compile_rejects_unclosable_linkage() -> None:
    with pytest.raises(InvalidCandidateError, match="cannot close"):
        compile_candidate(make_candidate(1000.0, 10.0, 10.0, 10.0))


def test_compile_rejects_non_finite_parameters() -> None:
    candidate = default_candidate(attempt_number=1)
    broken = candidate.model_copy(
        update={
            "parameters": FourBarParameters.model_construct(
                ground_length=math.nan,
                crank_length=35.0,
                coupler_length=135.0,
                rocker_length=100.0,
            )
        }
    )

    with pytest.raises(InvalidCandidateError, match="finite"):
        compile_candidate(broken)


def test_compile_rejects_non_positive_length() -> None:
    candidate = default_candidate(attempt_number=1)
    broken = candidate.model_copy(
        update={
            "parameters": FourBarParameters.model_construct(
                ground_length=0.0,
                crank_length=35.0,
                coupler_length=135.0,
                rocker_length=100.0,
            )
        }
    )

    with pytest.raises(InvalidCandidateError, match="positive"):
        compile_candidate(broken)


def test_compiled_model_loads_in_mujoco() -> None:
    mujoco = pytest.importorskip("mujoco")
    compiled = compile_candidate(make_candidate(95.0, 35.0, 135.0, 100.0, start=180.0))

    model = mujoco.MjModel.from_xml_string(compiled.mjcf_xml)

    assert model.nq == 3
    assert model.neq == 1
    assert model.joint("crank_hinge").qposadr[0] == 0
    assert model.site("rocker_tip").id >= 0
    assert model.site("coupler_end").id >= 0
