"""Design-program generation: the model writes CadQuery code for a part.

The model composes the design logic as code under a strict contract; the
sandbox executes it and independent checks verify the resulting mesh. The model
never decides pass/fail and never sees the evaluator thresholds.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.meta_client import MetaModelClient, ModelCompletion
from app.mechanism.schemas import (
    DeclaredParameter,
    DesignProgram,
    ExpectedBoundingBox,
    PartBrief,
)

PROGRAM_SYSTEM_PROMPT = """You write deterministic parametric CAD programs with CadQuery.
Return strict JSON matching the schema. The source field must contain Python that defines
build() returning a cadquery Workplane, Shape or Compound. Units are millimetres.

Rules for the program:
- Import only cadquery (optionally math). No other imports.
- Deterministic geometry: no randomness, time, environment, network or filesystem access.
- No dunder access, eval, exec, compile, open, os, sys, subprocess, pathlib or importlib.
- Produce one solid part that fits inside the requested bounding envelope.
- Keep loops bounded and primitives simple (box, cylinder, extrude, cut, union, fillet).

Declare the parameters you used and the bounding box you expect. Do not claim any checks
passed; an independent evaluator measures the exported mesh."""


class DeclaredParameterProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    value: float


class BBoxProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width_mm: float = Field(gt=0, le=10_000)
    height_mm: float = Field(gt=0, le=10_000)
    thickness_mm: float = Field(gt=0, le=1_000)


class ProgramProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["python"]
    entrypoint: Literal["build"]
    source: str = Field(min_length=50, max_length=20_000)
    declared_parameters: list[DeclaredParameterProposal]
    expected_bbox_mm: BBoxProposal
    notes: list[str]


def build_program_user_prompt(
    brief: PartBrief,
    *,
    attempt_number: int,
    max_attempts: int,
    previous_feedback: str | None = None,
) -> str:
    sections = [
        "Part requirements (authoritative):\n" + brief.model_dump_json(indent=2),
        f"This is program attempt {attempt_number} of {max_attempts}.",
    ]
    if previous_feedback:
        sections.append(
            "The previous program failed validation:\n"
            + previous_feedback
            + "\nRevise the program to fix these problems."
        )
    return "\n\n".join(sections)


async def generate_program(
    brief: PartBrief,
    *,
    client: MetaModelClient,
    attempt_number: int,
    max_attempts: int,
    previous_feedback: str | None = None,
) -> tuple[DesignProgram, ModelCompletion]:
    completion = await client.complete_json(
        system_prompt=PROGRAM_SYSTEM_PROMPT,
        user_prompt=build_program_user_prompt(
            brief,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            previous_feedback=previous_feedback,
        ),
        schema=ProgramProposal.model_json_schema(),
        schema_name="design_program",
    )
    proposal = ProgramProposal.model_validate(completion.payload)
    program = DesignProgram(
        program_id=f"program_{attempt_number:03d}",
        capability_id="custom_part",
        source=proposal.source,
        declared_parameters=[
            DeclaredParameter(name=item.name, value=item.value)
            for item in proposal.declared_parameters
        ],
        expected_bbox=ExpectedBoundingBox(
            width_mm=proposal.expected_bbox_mm.width_mm,
            height_mm=proposal.expected_bbox_mm.height_mm,
            thickness_mm=proposal.expected_bbox_mm.thickness_mm,
        ),
        notes=proposal.notes,
    )
    return program, completion


__all__ = [
    "PROGRAM_SYSTEM_PROMPT",
    "ProgramProposal",
    "build_program_user_prompt",
    "generate_program",
]
