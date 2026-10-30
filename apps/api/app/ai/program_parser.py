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


ASSEMBLY_PROGRAM_SYSTEM_PROMPT = """You write deterministic parametric CAD assemblies with
CadQuery. Return strict JSON matching the schema. The source field must contain Python that
defines build() returning a dict:

    {
      "parts": {"<part_name>": <cadquery Workplane|Shape|Compound>, ...},
      "joints": [
        {"name": "<joint_name>", "parent": "<part>", "child": "<part>",
         "origin": [x, y, z], "axis": [x, y, z], "min_deg": -90, "max_deg": 90}
      ]
    }

Rules:
- Import only cadquery (optionally math). No other imports.
- Deterministic geometry: no randomness, time, environment, network or filesystem access.
- No dunder access, eval, exec, compile, open, os, sys, subprocess, pathlib or importlib.
- 2 to 12 parts, at most 6 revolute joints, part names matching [A-Za-z0-9_].
- Model the assembly in its assembled pose, inside the requested bounding envelope.
- Every part must be a closed, non-empty solid in millimetres.
- The two parts joined by each joint must not interpenetrate at any angle within its limits;
  an independent check rotates the child part about the declared axis and detects penetrations
  deeper than 0.2 mm.
- For hinges, offset the leaf planes away from the joint axis so the rotating leaf cannot sweep
  through the other leaf (for example shift each plate by at least its thickness plus 1 mm, or
  start the plates beyond the knuckle radius). Interleave knuckles along the pin with axial gaps,
  and keep the assembled state inside the requested envelope.
- Keep loops bounded and primitives simple (box, cylinder, extrude, cut, union).

Do not claim any checks passed; an independent evaluator measures the exported parts."""


STRUCTURE_PROGRAM_SYSTEM_PROMPT = """You write deterministic parametric CAD structures with
CadQuery. Return strict JSON matching the schema. The source field must contain Python that
defines build() returning a dict:

    {"parts": {"<part_name>": <cadquery Workplane|Shape|Compound>, ...}}

Joints are not needed for static structures. Rules:
- Import only cadquery (optionally math). No other imports.
- Deterministic geometry: no randomness, time, environment, network or filesystem access.
- No dunder access, eval, exec, compile, open, os, sys, subprocess, pathlib or importlib.
- 2 to 80 parts, part names matching [A-Za-z0-9_].
- Model the structure in its assembled pose and fit inside the requested envelope: the measured
  overall length, width and height (including connection plates and overhangs) must not exceed
  the brief's dimensions by more than 5%. The requested length and width are hard maximums:
  model the main span about 2-3% shorter so end plates and overhangs stay inside the envelope.
- CadQuery API: use only cq.Workplane (box, cylinder, hole, extrude, cut, union, translate,
  rotate), cq.Vector, cq.Shape and cq.Compound. Do not use cq.Quaternion or other unverified
  APIs. Define helper functions with all required arguments and call them correctly; keep the
  code simple and self-contained.
- Every part must be a closed, non-empty solid in millimetres.
- Connection plates, bolt holes and overlaps at joints are allowed; only closed solids, overall
  dimensions and determinism are verified. No structural analysis is performed.
- Keep loops bounded and primitives simple (box, cylinder, extrude, cut, union).

Do not claim any checks passed; an independent evaluator measures the exported parts."""


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
    assembly: bool = False,
    structure: bool = False,
    capability_id: str = "custom_part",
) -> tuple[DesignProgram, ModelCompletion]:
    if structure:
        system_prompt = STRUCTURE_PROGRAM_SYSTEM_PROMPT
    elif assembly:
        system_prompt = ASSEMBLY_PROGRAM_SYSTEM_PROMPT
    else:
        system_prompt = PROGRAM_SYSTEM_PROMPT
    request = {
        "system_prompt": system_prompt,
        "user_prompt": build_program_user_prompt(
            brief,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            previous_feedback=previous_feedback,
        ),
        "schema": ProgramProposal.model_json_schema(),
        "schema_name": "design_program",
    }
    completion = await client.complete_json(**request)
    try:
        proposal = ProgramProposal.model_validate(completion.payload)
    except Exception:
        # One bounded retry for malformed or truncated structured output.
        completion = await client.complete_json(**request)
        proposal = ProgramProposal.model_validate(completion.payload)
    program = DesignProgram(
        program_id=f"program_{attempt_number:03d}",
        capability_id=capability_id,
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
    "ASSEMBLY_PROGRAM_SYSTEM_PROMPT",
    "STRUCTURE_PROGRAM_SYSTEM_PROMPT",
    "PROGRAM_SYSTEM_PROMPT",
    "ProgramProposal",
    "build_program_user_prompt",
    "generate_program",
]
