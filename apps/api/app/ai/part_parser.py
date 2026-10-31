"""Requirements parsing for model-authored static parts.

The model decides whether a request is a single static part that fits inside a
bounding envelope; anything else is reported unsupported instead of being
silently coerced into a part. The deterministic honesty floor from the
four-bar path (loads, temperatures, unmodelled motion) still applies.
"""

import re
from dataclasses import dataclass
from typing import Literal

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

Set supported=false with a short reason when the request asks for multiple separate parts or
components that move relative to each other (for example a gripper with fingers and rails);
do not reduce a multi-part request to one part. When you produce simplified geometry for a
larger product, name exactly what geometry is being produced in description, and list every
omitted component, mechanism and analysis in unsupported_requirements (for example a visor
mechanism, padding, impact protection or certification).

Set required_components to named physical parts the request expects (usually empty for a
single part; features such as bores, ribs, holes and fillets belong in description and must
not be listed as components) and required_motion to the dominant relative motion (none for
a single static part).

Record inferred values in assumptions, mark provenance, and ask a blocking clarification
question only when missing information would materially change the part. Do not invent
requirements the request does not state."""


ASSEMBLY_SYSTEM_PROMPT = """You convert a mechanical design request into strict JSON for a
small mechanical assembly of solids connected by joints (for example a hinge with leaves,
knuckles and a pin, a clevis bracket, or a gripper with sliding fingers and guide rails). Use
millimetres and give the bounding envelope of the whole assembled mechanism.

The envelope must include every part and the clearance needed for the declared motion, not just
the mounting plate or base. Derive it from the component dimensions in the request (plus their
travel) and record the estimate in assumptions. If an overall dimension is missing and would
materially change the assembly, ask a blocking clarification question for it.

Set supported=false with a short reason only when no meaningful assembly can represent part of
the request. When the request is larger than a single assembly, name exactly what is produced in
description and list every omitted component, mechanism and analysis in
unsupported_requirements.

Set required_components to separate physical parts (for example leaf_left, leaf_right, pin)
and required_motion to the relative motion between parts. Holes, bores, slots, bosses, ribs and
fillets in a part are features, not components, and a hole or pin hole is not a joint; do not set
rotary or prismatic motion from them. If the request describes one static part, set
required_motion=none (the router normally sends single parts to the part capability).

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
the request does not state.

Set required_components to the named members and parts the request expects (for example a deck,
chords, braces and connection plates) and required_motion to none for a static structure."""


class PartBriefProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported: bool
    reason: str
    description: str = Field(min_length=1, max_length=2000)
    max_width_mm: float = Field(gt=0, le=100_000)
    max_height_mm: float = Field(gt=0, le=100_000)
    max_thickness_mm: float = Field(gt=0, le=100_000)
    assumptions: list[str]
    unknowns: list[str]
    unsupported_requirements: list[str]
    required_components: list[str]
    required_motion: Literal["rotary", "prismatic", "none"]
    clarification_questions: list[ClarificationQuestionProposal]
    requirement_sources: list[RequirementSourceProposal]


_SUPPORTED_HINTS = (
    "can be",
    "suitable",
    "represent",
    "decompos",
    "can model",
    "feasible",
    "meaningful",
)


_MOTION_WORDS = (
    "rotate",
    "rotat",
    "pivot",
    "hinge",
    "slide",
    "sliding",
    "joint",
    "finger",
    "gripper",
    "rail",
    "actuator",
    "moving",
    "moves",
    "turns",
    "drives",
)

_PART_CONFUSION_HINTS = (
    "multiple",
    "separate",
    "not a single",
    "component",
    "parts",
    "assembly",
)

_FEATURE_WORDS = (
    "bore",
    "hole",
    "rib",
    "fillet",
    "bearing",
    "seat",
    "mount",
    "bracket",
    "housing",
    "plate",
    "enclosure",
    "flange",
    "boss",
    "pocket",
    "slot",
    "chamfer",
)


def _reason_reads_supported(reason: str) -> bool:
    lowered = reason.lower()
    return any(hint in lowered for hint in _SUPPORTED_HINTS)


def _refusal_looks_like_feature_confusion(reason: str, prompt: str) -> bool:
    """A single part with bores, holes, ribs and fillets is often misread as multi-part."""
    lowered_prompt = prompt.lower()
    if any(word in lowered_prompt for word in _MOTION_WORDS):
        return False
    if not any(word in lowered_prompt for word in _FEATURE_WORDS):
        return False
    lowered_reason = reason.lower()
    return any(hint in lowered_reason for hint in _PART_CONFUSION_HINTS)


_LENGTH_PATTERN = re.compile(
    r"overall\s+length[^0-9]{0,30}?([\d,]+(?:\.\d+)?)\s*mm", re.IGNORECASE
)
_WIDTH_PATTERN = re.compile(
    r"(?:deck\s+)?width[^0-9]{0,30}?([\d,]+(?:\.\d+)?)\s*mm", re.IGNORECASE
)
_HEIGHT_PATTERNS = (
    re.compile(
        r"towers?[^0-9]{0,40}?([\d,]+(?:\.\d+)?)\s*mm\s*high", re.IGNORECASE
    ),
    re.compile(
        r"height[^0-9]{0,30}?([\d,]+(?:\.\d+)?)\s*mm", re.IGNORECASE
    ),
)


def extract_structure_dimensions(prompt: str) -> dict[str, float] | None:
    """Extract overall length, width and height when all are stated."""
    def _value(pattern: re.Pattern[str]) -> float | None:
        match = pattern.search(prompt)
        if match is None:
            return None
        return float(match.group(1).replace(",", ""))

    length = _value(_LENGTH_PATTERN)
    width = _value(_WIDTH_PATTERN)
    height = None
    for pattern in _HEIGHT_PATTERNS:
        height = _value(pattern)
        if height is not None:
            break
    if length is None or width is None or height is None:
        return None
    return {"length_mm": length, "width_mm": width, "height_mm": height}


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

    async def reask(correction: str) -> PartBriefProposal:
        retry = await client.complete_json(
            system_prompt=system_prompt,
            user_prompt=prompt + "\n\n" + correction,
            schema=PartBriefProposal.model_json_schema(),
            schema_name="part_brief",
        )
        return PartBriefProposal.model_validate(retry.payload)

    retried = False
    if not proposal.supported and _reason_reads_supported(proposal.reason):
        # The model sometimes sets supported=false while describing a request it
        # can model. Ask once more with an explicit correction.
        proposal = await reask(
            "Re-evaluate: if this request can be modeled as a static structure or "
            "part made of solids, set supported=true. Set supported=false only when "
            "a required capability genuinely does not exist."
        )
        retried = True
    if (
        not proposal.supported
        and not retried
        and not assembly
        and not structure
        and _refusal_looks_like_feature_confusion(proposal.reason, prompt)
    ):
        proposal = await reask(
            "Re-evaluate: this request describes one static part whose bores, holes, "
            "ribs, fillets and similar details are features of that single solid, not "
            "separate components or moving parts. Set supported=true and model them in "
            "one part; set supported=false only if separate moving parts are required."
        )
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
    dimensions = None
    if structure:
        dimensions = extract_structure_dimensions(prompt)
    assumptions = list(proposal.assumptions)
    if dimensions is not None:
        assumptions.append(
            "Overall dimensions taken from the request: "
            f"{dimensions['length_mm']:.0f} x {dimensions['width_mm']:.0f} x "
            f"{dimensions['height_mm']:.0f} mm (length x width x height)."
        )
    brief = PartBrief(
        part=PartRequirements(
            description=proposal.description,
            max_width_mm=(
                dimensions["length_mm"]
                if dimensions is not None
                else proposal.max_width_mm
            ),
            max_height_mm=(
                dimensions["width_mm"]
                if dimensions is not None
                else proposal.max_height_mm
            ),
            max_thickness_mm=(
                dimensions["height_mm"]
                if dimensions is not None
                else proposal.max_thickness_mm
            ),
        ),
        assumptions=assumptions,
        unknowns=proposal.unknowns,
        unsupported_requirements=proposal.unsupported_requirements,
        required_components=proposal.required_components,
        required_motion=proposal.required_motion,
        clarification_questions=questions,
        requirement_sources={
            item.field: item.source for item in proposal.requirement_sources
        },
    )
    return PartRequirementsResult(brief=brief, reason=None, completion=completion)


__all__ = [
    "ASSEMBLY_SYSTEM_PROMPT",
    "extract_structure_dimensions",
    "STRUCTURE_SYSTEM_PROMPT",
    "PART_SYSTEM_PROMPT",
    "PartBriefProposal",
    "PartRequirementsResult",
    "parse_part_requirements",
]
