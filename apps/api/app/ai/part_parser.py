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
static parametric part. Set supported=false with a short reason when the request is not a
single static part inside a bounding envelope (for example a whole vehicle, a moving
assembly or a multi-component product). Use millimetres. Estimate a practical bounding
envelope from the request. Record inferred values in assumptions, mark provenance, and ask
a blocking clarification question only when missing information would materially change the
part. Do not invent requirements the request does not state."""


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
) -> PartRequirementsResult:
    completion = await client.complete_json(
        system_prompt=PART_SYSTEM_PROMPT,
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
    questions = _merge_questions(questions, policy_clarification_questions(prompt))
    brief = PartBrief(
        part=PartRequirements(
            description=proposal.description,
            max_width_mm=proposal.max_width_mm,
            max_height_mm=proposal.max_height_mm,
            max_thickness_mm=proposal.max_thickness_mm,
        ),
        assumptions=proposal.assumptions,
        unknowns=proposal.unknowns,
        clarification_questions=questions,
        requirement_sources={
            item.field: item.source for item in proposal.requirement_sources
        },
    )
    return PartRequirementsResult(brief=brief, reason=None, completion=completion)


__all__ = [
    "PART_SYSTEM_PROMPT",
    "PartBriefProposal",
    "PartRequirementsResult",
    "parse_part_requirements",
]
