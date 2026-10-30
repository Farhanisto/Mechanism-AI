"""Requirements parsing for model-authored static parts.

The model decides whether a request is a single static part that fits inside a
bounding envelope; anything else is reported unsupported instead of being
silently coerced into a part. The deterministic honesty floor from the
four-bar path (loads, temperatures, unmodelled motion) still applies.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from app.ai.meta_client import MetaModelClient, ModelCompletion
from app.ai.requirements_parser import (
    ClarificationQuestionProposal,
    RequirementSourceProposal,
    _merge_questions,
    policy_clarification_questions,
)
from app.mechanism.schemas import ClarificationQuestion, PartBrief, PartRequirements

PART_SYSTEM_PROMPT = """You convert a mechanical design request into strict JSON for one
static solid part, or a simplified representative geometry when the full product is out of
scope (for example a mounting plate, bracket, spacer, shell or enclosure body). Use
millimetres and estimate a practical bounding envelope from the request.

Set supported=false with a short reason only when no meaningful single solid can represent
part of the request. When you produce simplified geometry for a larger product, name exactly
what geometry is being produced in description, and list every omitted component, mechanism
and analysis in unsupported_requirements (for example a visor mechanism, padding, impact
protection or certification).

Record inferred values in assumptions, mark provenance, and ask a blocking clarification
question only when missing information would materially change the part. Do not invent
requirements the request does not state."""


ASSEMBLY_SYSTEM_PROMPT = """You convert a mechanical design request into strict JSON for a
small mechanical assembly of static solids connected by revolute joints (for example a hinge
with leaves, knuckles and a pin, or a clevis bracket). Use millimetres and give the bounding
envelope of the assembled state.

Set supported=false with a short reason only when no meaningful assembly can represent part of
the request. When the request is larger than a single assembly, name exactly what is produced in
description and list every omitted component, mechanism and analysis in
unsupported_requirements.

Record inferred values in assumptions, mark provenance, and ask a blocking clarification question
only when missing information would materially change the assembly. Do not invent requirements
the request does not state."""


STRUCTURE_SYSTEM_PROMPT = """You convert a mechanical design request into strict JSON for a
static structural frame made of multiple solid parts (for example a truss bridge, beam frame or
lattice structure). Use millimetres and give the bounding envelope of the assembled structure.
Map the requested overall dimensions into the envelope: longest span or length -> max_width_mm,
width -> max_height_mm, height -> max_thickness_mm. When the height is not stated, choose a
realistic value for the structure (for a truss, roughly span/6 to span/4) and record it as an
assumption.

Set supported=false with a short reason only when no meaningful static structure can represent
part of the request. When the request is larger than a single structure, name exactly what is
produced in description and list every omitted component, mechanism and analysis in
unsupported_requirements (for example load capacity, deflection, connection strength or
certification).

Record inferred values in assumptions, mark provenance, and ask a blocking clarification question
only when missing information would materially change the structure. Do not invent requirements
the request does not state."""


class PartBriefProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported: bool
    reason: str
    description: str = Field(min_length=1, max_length=2000)
    max_width_mm: float = Field(gt=0, le=10_000)
    max_height_mm: float = Field(gt=0, le=10_000)
    max_thickness_mm: float = Field(gt=0, le=1_000)
    assumptions: list[str]
    unknowns: list[str]
    unsupported_requirements: list[str]
    clarification_questions: list[ClarificationQuestionProposal]
    requirement_sources: list[RequirementSourceProposal]


@dataclass(frozen=True)
class PartRequirementsResult:
    brief: PartBrief | None
    reason: str | None
    completion: ModelCompletion


async def parse_part_requirements(
    prompt: str,
    *,
    client: MetaModelClient,
    assembly: bool = False,
    structure: bool = False,
) -> PartRequirementsResult:
    if structure:
        system_prompt = STRUCTURE_SYSTEM_PROMPT
    elif assembly:
        system_prompt = ASSEMBLY_SYSTEM_PROMPT
    else:
        system_prompt = PART_SYSTEM_PROMPT
    completion = await client.complete_json(
        system_prompt=system_prompt,
        user_prompt=prompt,
        schema=PartBriefProposal.model_json_schema(),
        schema_name="part_brief",
    )
    proposal = PartBriefProposal.model_validate(completion.payload)
    if not proposal.supported:
        return PartRequirementsResult(
            brief=None,
            reason=proposal.reason or "the request is not a single static part",
            completion=completion,
        )
    questions = [
        ClarificationQuestion(
            question_id=item.question_id,
            question=item.question,
            field=item.field,
            blocking=item.blocking,
        )
        for item in proposal.clarification_questions
    ]
    questions = _merge_questions(
        questions, policy_clarification_questions(prompt, include_motion=False)
    )
    brief = PartBrief(
        part=PartRequirements(
            description=proposal.description,
            max_width_mm=proposal.max_width_mm,
            max_height_mm=proposal.max_height_mm,
            max_thickness_mm=proposal.max_thickness_mm,
        ),
        assumptions=proposal.assumptions,
        unknowns=proposal.unknowns,
        unsupported_requirements=proposal.unsupported_requirements,
        clarification_questions=questions,
        requirement_sources={
            item.field: item.source for item in proposal.requirement_sources
        },
    )
    return PartRequirementsResult(brief=brief, reason=None, completion=completion)


__all__ = [
    "ASSEMBLY_SYSTEM_PROMPT",
    "STRUCTURE_SYSTEM_PROMPT",
    "PART_SYSTEM_PROMPT",
    "PartBriefProposal",
    "PartRequirementsResult",
    "parse_part_requirements",
]
