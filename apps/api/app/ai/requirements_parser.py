import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.meta_client import MetaModelClient, ModelCompletion
from app.capabilities.router import detected_demand_categories
from app.mechanism.schemas import (
    ClarificationQuestion,
    HardConstraints,
    MechanismType,
    NormalizedBrief,
    RequirementSource,
    TargetMotion,
    TargetMotionType,
    Units,
)

REQUIREMENTS_SYSTEM_PROMPT = """You convert a mechanical design brief into strict JSON.
Return only a JSON object matching the supplied schema. Use millimetres and the
four-bar linkage mechanism. Record every value you had to infer in assumptions.
Mark the provenance of each requirement in requirement_sources, put anything
missing in unknowns, ask a blocking clarification question only when an unknown
materially changes the design, and list required checks beyond the standard set
in requested_checks. Capture component CAD details when the prompt states them:
link width, link thickness and pivot hole diameter in millimetres, and whether
cylindrical pins should be included; use null/false when not stated. Do not
invent constraints that the prompt does not state; use the documented defaults
only when a critical value is missing."""

_STANDARD_ASSUMPTIONS = (
    "Output point is the rocker pin; the ground link is a fixed frame.",
    "Links are zero-thickness line segments; ground/frame contact is not a collision.",
)
_MM_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)
_MM_THICKNESS_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:thick|thickness)", re.IGNORECASE
)
_MM_HOLE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:pivot\s*)?holes?", re.IGNORECASE
)
_MM_WIDTH_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:wide|width)", re.IGNORECASE
)
_UNMODELED_MOTION_PATTERN = re.compile(
    r"\b(vertical|rotate|rotates|rotary|rotating|circular|spiral)\b",
    re.IGNORECASE,
)


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


class ClarificationQuestionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=400)
    field: str = Field(min_length=1, max_length=120)
    blocking: bool


class RequirementSourceProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=120)
    source: Literal["user_provided", "ai_proposed", "default_assumption"]


class BriefProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism_type: Literal["four_bar_linkage"]
    units: Literal["mm"]
    target_motion: TargetMotionProposal
    constraints: ConstraintsProposal
    assumptions: list[str]
    unknowns: list[str]
    clarification_questions: list[ClarificationQuestionProposal]
    requirement_sources: list[RequirementSourceProposal]
    requested_checks: list[str]
    link_width_mm: float | None
    link_thickness_mm: float | None
    pivot_hole_mm: float | None
    include_pins: bool


def policy_clarification_questions(
    prompt: str, *, include_motion: bool = True
) -> list[ClarificationQuestion]:
    """Deterministic honesty floor: ask about anything the evaluator cannot verify.

    These questions are asked in addition to any the model proposes; they pause
    the run until the user answers because the answers materially change the
    acceptance scope.
    """
    questions: list[ClarificationQuestion] = []
    if detected_demand_categories(prompt):
        questions.append(
            ClarificationQuestion(
                question_id="verification_scope",
                question=(
                    "The request involves conditions or certifications the current "
                    "evaluator cannot verify (for example loads, temperature, dynamics "
                    "or safety certification). Continue with geometric and (where "
                    "applicable) kinematic checks only?"
                ),
                field="verification_scope.kinematic_only",
                blocking=True,
            )
        )
    input_motion_described = re.search(r"\b(input|crank)\b", prompt, re.IGNORECASE)
    if (
        include_motion
        and _UNMODELED_MOTION_PATTERN.search(prompt)
        and not input_motion_described
    ):
        questions.append(
            ClarificationQuestion(
                question_id="target_motion_type",
                question=(
                    "The request describes motion the evaluator does not model (for "
                    "example vertical or continuous rotary motion). Should the output "
                    "target be near-horizontal travel?"
                ),
                field="target_motion.type",
                blocking=True,
            )
        )
    return questions


def _merge_questions(
    proposed: list[ClarificationQuestion],
    policy: list[ClarificationQuestion],
) -> list[ClarificationQuestion]:
    merged = list(proposed)
    known_fields = {question.field for question in merged}
    for question in policy:
        if question.field not in known_fields:
            merged.append(question)
    return merged


def _with_standard_assumptions(brief: NormalizedBrief) -> NormalizedBrief:
    assumptions = list(brief.assumptions)
    for assumption in _STANDARD_ASSUMPTIONS:
        if assumption not in assumptions:
            assumptions.append(assumption)
    return brief.model_copy(update={"assumptions": assumptions})


def _extract_spec(pattern: re.Pattern[str], prompt: str) -> float | None:
    match = pattern.search(prompt)
    return float(match.group(1)) if match else None


def apply_prompt_cad_specs(brief: NormalizedBrief, prompt: str) -> NormalizedBrief:
    """Fill component CAD specs the model left unset with explicit prompt values."""
    updates: dict[str, object] = {}
    sources = dict(brief.requirement_sources)
    if brief.link_thickness_mm is None:
        value = _extract_spec(_MM_THICKNESS_PATTERN, prompt)
        if value is not None:
            updates["link_thickness_mm"] = value
            sources["link_thickness_mm"] = RequirementSource.USER_PROVIDED
    if brief.pivot_hole_mm is None:
        value = _extract_spec(_MM_HOLE_PATTERN, prompt)
        if value is not None:
            updates["pivot_hole_mm"] = value
            sources["pivot_hole_mm"] = RequirementSource.USER_PROVIDED
    if brief.link_width_mm is None:
        value = _extract_spec(_MM_WIDTH_PATTERN, prompt)
        if value is not None:
            updates["link_width_mm"] = value
            sources["link_width_mm"] = RequirementSource.USER_PROVIDED
    if not brief.include_pins and re.search(r"\bpins?\b", prompt, re.IGNORECASE):
        updates["include_pins"] = True
        sources["include_pins"] = RequirementSource.USER_PROVIDED
    if not updates:
        return brief
    updates["requirement_sources"] = sources
    return brief.model_copy(update=updates)


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

    link_thickness = _extract_spec(_MM_THICKNESS_PATTERN, prompt)
    pivot_hole = _extract_spec(_MM_HOLE_PATTERN, prompt)
    link_width = _extract_spec(_MM_WIDTH_PATTERN, prompt)
    include_pins = bool(re.search(r"\bpins?\b", prompt, re.IGNORECASE))

    assumptions = [
        "Near-horizontal target interpreted as a straight level output path.",
    ]
    if not found_travel:
        assumptions.append("Travel distance defaulted to 100 mm.")
    if not found_footprint:
        assumptions.append("Maximum footprint defaulted to 200 mm.")
    if not found_tolerance:
        assumptions.append("Trajectory tolerance defaulted to 5 mm.")

    requirement_sources = {
        "target_motion.type": RequirementSource.DEFAULT_ASSUMPTION,
        "target_motion.travel_distance": (
            RequirementSource.USER_PROVIDED
            if found_travel
            else RequirementSource.DEFAULT_ASSUMPTION
        ),
        "target_motion.trajectory_tolerance": (
            RequirementSource.USER_PROVIDED
            if found_tolerance
            else RequirementSource.DEFAULT_ASSUMPTION
        ),
        "constraints.max_footprint": (
            RequirementSource.USER_PROVIDED
            if found_footprint
            else RequirementSource.DEFAULT_ASSUMPTION
        ),
        **(
            {"link_thickness_mm": RequirementSource.USER_PROVIDED}
            if link_thickness is not None
            else {}
        ),
        **(
            {"pivot_hole_mm": RequirementSource.USER_PROVIDED}
            if pivot_hole is not None
            else {}
        ),
        **(
            {"link_width_mm": RequirementSource.USER_PROVIDED}
            if link_width is not None
            else {}
        ),
        **(
            {"include_pins": RequirementSource.USER_PROVIDED} if include_pins else {}
        ),
    }
    unknowns = [
        field
        for field, source in requirement_sources.items()
        if source is RequirementSource.DEFAULT_ASSUMPTION and field != "target_motion.type"
    ]

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
            unknowns=unknowns,
            link_width_mm=link_width,
            link_thickness_mm=link_thickness,
            pivot_hole_mm=pivot_hole,
            include_pins=include_pins,
            clarification_questions=policy_clarification_questions(prompt),
            requirement_sources=requirement_sources,
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
    proposal = BriefProposal.model_validate(completion.payload)
    brief = NormalizedBrief.model_validate(
        {
            "mechanism_type": proposal.mechanism_type,
            "units": proposal.units,
            "target_motion": proposal.target_motion.model_dump(),
            "constraints": proposal.constraints.model_dump(),
            "assumptions": proposal.assumptions,
            "unknowns": proposal.unknowns,
            "clarification_questions": [
                question.model_dump() for question in proposal.clarification_questions
            ],
            "requirement_sources": {
                item.field: item.source for item in proposal.requirement_sources
            },
            "requested_checks": proposal.requested_checks,
            "link_width_mm": proposal.link_width_mm,
            "link_thickness_mm": proposal.link_thickness_mm,
            "pivot_hole_mm": proposal.pivot_hole_mm,
            "include_pins": proposal.include_pins,
        }
    )
    brief = brief.model_copy(
        update={
            "clarification_questions": _merge_questions(
                brief.clarification_questions,
                policy_clarification_questions(prompt),
            )
        }
    )
    return _with_standard_assumptions(brief), completion
