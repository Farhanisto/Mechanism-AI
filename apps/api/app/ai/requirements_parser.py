import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.meta_client import MetaModelClient, ModelCompletion
from app.mechanism.schemas import (
    HardConstraints,
    MechanismType,
    NormalizedBrief,
    TargetMotion,
    TargetMotionType,
    Units,
)

REQUIREMENTS_SYSTEM_PROMPT = """You convert a mechanical design brief into strict JSON.
Return only a JSON object matching the supplied schema. Use millimetres and the
four-bar linkage mechanism. Record every value you had to infer in assumptions.
Do not invent constraints that the prompt does not state; use the documented
defaults only when a critical value is missing."""

_STANDARD_ASSUMPTIONS = (
    "Output point is the rocker pin; the ground link is a fixed frame.",
    "Links are zero-thickness line segments; ground/frame contact is not a collision.",
)
_MM_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)


class TargetMotionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["near_horizontal"]
    travel_distance: float = Field(gt=0, le=10_000)
    trajectory_tolerance: float = Field(gt=0, le=100)


class ConstraintsProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_footprint: float = Field(gt=0, le=10_000)
    complete_motion_cycle: bool
    avoid_collisions: bool


class BriefProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism_type: Literal["four_bar_linkage"]
    units: Literal["mm"]
    target_motion: TargetMotionProposal
    constraints: ConstraintsProposal
    assumptions: list[str]


def _with_standard_assumptions(brief: NormalizedBrief) -> NormalizedBrief:
    assumptions = list(brief.assumptions)
    for assumption in _STANDARD_ASSUMPTIONS:
        if assumption not in assumptions:
            assumptions.append(assumption)
    return brief.model_copy(update={"assumptions": assumptions})


def _number_near(
    prompt: str,
    keywords: tuple[str, ...],
    *,
    default: float,
    used_positions: set[int],
) -> tuple[float, bool]:
    for match in _MM_PATTERN.finditer(prompt):
        if match.start() in used_positions:
            continue
        context = prompt[max(0, match.start() - 50) : match.end() + 50].lower()
        if any(keyword in context for keyword in keywords):
            used_positions.add(match.start())
            return float(match.group("value")), True
    return default, False


def default_brief_from_prompt(prompt: str) -> NormalizedBrief:
    """Deterministic brief used when no Meta API key is configured.

    This is intentionally simple and records every inferred value. It keeps the
    demo pipeline useful without a network call without pretending to be AI.
    """
    used_positions: set[int] = set()
    travel, found_travel = _number_near(
        prompt,
        ("travel", "movement", "stroke", "displacement"),
        default=100.0,
        used_positions=used_positions,
    )
    footprint, found_footprint = _number_near(
        prompt,
        ("footprint", "envelope", "fits within", "package"),
        default=200.0,
        used_positions=used_positions,
    )
    tolerance, found_tolerance = _number_near(
        prompt,
        ("tolerance", "accuracy", "within"),
        default=5.0,
        used_positions=used_positions,
    )

    assumptions = [
        "Near-horizontal target interpreted as a straight level output path.",
    ]
    if not found_travel:
        assumptions.append("Travel distance defaulted to 100 mm.")
    if not found_footprint:
        assumptions.append("Maximum footprint defaulted to 200 mm.")
    if not found_tolerance:
        assumptions.append("Trajectory tolerance defaulted to 5 mm.")

    return _with_standard_assumptions(
        NormalizedBrief(
            mechanism_type=MechanismType.FOUR_BAR_LINKAGE,
            units=Units.MM,
            target_motion=TargetMotion(
                type=TargetMotionType.NEAR_HORIZONTAL,
                travel_distance=travel,
                trajectory_tolerance=tolerance,
            ),
            constraints=HardConstraints(
                max_footprint=footprint,
                complete_motion_cycle=True,
                avoid_collisions=True,
            ),
            assumptions=assumptions,
        )
    )


async def parse_requirements(
    prompt: str,
    *,
    client: MetaModelClient,
) -> tuple[NormalizedBrief, ModelCompletion]:
    completion = await client.complete_json(
        system_prompt=REQUIREMENTS_SYSTEM_PROMPT,
        user_prompt=prompt,
        schema=BriefProposal.model_json_schema(),
        schema_name="normalized_brief",
    )
    brief = NormalizedBrief.model_validate(completion.payload)
    return _with_standard_assumptions(brief), completion
