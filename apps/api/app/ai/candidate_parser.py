import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.meta_client import MetaModelClient, ModelCompletion
from app.mechanism.schemas import (
    Candidate,
    Evaluation,
    FourBarParameters,
    InputMotion,
    MechanismType,
    NormalizedBrief,
)

CANDIDATE_SYSTEM_PROMPT = """You propose planar four-bar linkage parameters as strict JSON.
Return only an object matching the supplied schema. Use millimetres and degrees.
Conventions: O2=(0,0), O4=(ground_length,0), input angles are counter-clockwise
from +x, and the output point is the rocker pin. Propose a closed crank-rocker
that can complete a full input rotation; prefer start_angle_deg=0 and
end_angle_deg=360. Do not return code, units, or fields not in the schema.

Design guidance:
- Make the shortest link the crank so the linkage is a Grashof crank-rocker.
- Keep every joint inside max_footprint with at least 10% margin.
- Match the requested output travel; near-horizontal means a level, straight path.
- A useful starting region for travel T is ground ~0.9T to 0.95T,
  crank ~0.3T to 0.4T, coupler ~1.25T to 1.4T, rocker ~0.9T to 1.1T.
  Adjust it to respect max_footprint and recheck the full 360-degree cycle.
- Allowed ranges: link lengths are positive and at most 10000 mm; input angles
  are between -3600 and 3600 degrees."""

_FALLBACK_LINKAGES: tuple[tuple[float, float, float, float], ...] = (
    (95.0, 35.0, 135.0, 100.0),
    (100.0, 38.0, 130.0, 95.0),
    (90.0, 35.0, 130.0, 105.0),
)


class FourBarParametersProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ground_length: float = Field(gt=0, le=10_000)
    crank_length: float = Field(gt=0, le=10_000)
    coupler_length: float = Field(gt=0, le=10_000)
    rocker_length: float = Field(gt=0, le=10_000)


class InputMotionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_angle_deg: float = Field(ge=-3600, le=3600)
    end_angle_deg: float = Field(ge=-3600, le=3600)


class CandidateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism_type: Literal["four_bar_linkage"]
    parameters: FourBarParametersProposal
    input_motion: InputMotionProposal


def parse_candidate(
    payload: dict[str, Any],
    *,
    candidate_id: str,
    attempt_number: int,
) -> Candidate:
    """Validate untrusted model output into a typed candidate."""
    proposal = CandidateProposal.model_validate(payload)
    return Candidate(
        candidate_id=candidate_id,
        mechanism_type=MechanismType(proposal.mechanism_type),
        parameters=FourBarParameters.model_validate(proposal.parameters.model_dump()),
        input_motion=InputMotion.model_validate(proposal.input_motion.model_dump()),
        generated_at=datetime.now(UTC),
        attempt_number=attempt_number,
    )


def default_candidate(
    *,
    attempt_number: int,
    candidate_id: str | None = None,
) -> Candidate:
    """Deterministic fallback candidate for offline runs and tests."""
    index = min(attempt_number - 1, len(_FALLBACK_LINKAGES) - 1)
    ground, crank, coupler, rocker = _FALLBACK_LINKAGES[index]
    return Candidate(
        candidate_id=candidate_id or f"candidate_{attempt_number:03d}",
        mechanism_type=MechanismType.FOUR_BAR_LINKAGE,
        parameters=FourBarParameters(
            ground_length=ground,
            crank_length=crank,
            coupler_length=coupler,
            rocker_length=rocker,
        ),
        input_motion=InputMotion(start_angle_deg=0, end_angle_deg=360),
        generated_at=datetime.now(UTC),
        attempt_number=attempt_number,
    )


def build_candidate_user_prompt(
    brief: NormalizedBrief,
    *,
    attempt_number: int,
    max_attempts: int | None = None,
    previous_candidate: Candidate | None = None,
    previous_evaluation: Evaluation | None = None,
) -> str:
    sections = [
        "Design brief (authoritative):\n" + brief.model_dump_json(indent=2),
    ]
    if previous_candidate is not None and previous_evaluation is not None:
        sections.append(
            "Previous candidate:\n"
            + previous_candidate.model_dump_json(
                indent=2,
                exclude={"generated_at", "candidate_id"},
            )
        )
        sections.append(
            "Independent evaluation of that candidate:\n"
            + json.dumps(
                {
                    "status": previous_evaluation.status.value,
                    "metrics": previous_evaluation.metrics.model_dump(mode="json"),
                    "failed_constraints": previous_evaluation.failed_constraints,
                    "diagnostic_notes": previous_evaluation.diagnostic_notes,
                },
                indent=2,
            )
        )
        sections.append(
            "Propose a revised candidate that fixes the failed constraints. "
            "Do not change the requirements and do not claim success."
        )
    if max_attempts is None:
        sections.append(f"This is candidate attempt {attempt_number}.")
    else:
        sections.append(f"This is candidate attempt {attempt_number} of {max_attempts}.")
    return "\n\n".join(sections)


async def generate_candidate(
    brief: NormalizedBrief,
    *,
    client: MetaModelClient,
    attempt_number: int,
    max_attempts: int | None = None,
    previous_candidate: Candidate | None = None,
    previous_evaluation: Evaluation | None = None,
) -> tuple[Candidate, ModelCompletion]:
    completion = await client.complete_json(
        system_prompt=CANDIDATE_SYSTEM_PROMPT,
        user_prompt=build_candidate_user_prompt(
            brief,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            previous_candidate=previous_candidate,
            previous_evaluation=previous_evaluation,
        ),
        schema=CandidateProposal.model_json_schema(),
        schema_name="four_bar_candidate",
    )
    return (
        parse_candidate(
            completion.payload,
            candidate_id=f"candidate_{attempt_number:03d}",
            attempt_number=attempt_number,
        ),
        completion,
    )
