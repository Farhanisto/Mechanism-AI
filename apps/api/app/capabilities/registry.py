"""Capability registry: which engineering operations the product actually has.

Every capability that can be selected by the router must have a registry entry
defining its contract, available evaluation checks and test status. A capability
whose generation and validation paths have not passed their tests is never
advertised as supported (PRD §7).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.mechanism.schemas import CapabilitySupport


class CapabilityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    version: str
    domain: str
    input_schema: str
    output_schema: str
    units: str
    parameter_constraints: dict[str, str] = Field(default_factory=dict)
    evaluation_checks: tuple[str, ...] = ()
    known_limitations: tuple[str, ...] = ()
    resource_limits: dict[str, float] = Field(default_factory=dict)
    test_status: Literal["tested", "untested"] = "untested"
    domain_terms: tuple[str, ...] = ()

    def is_selectable(self) -> bool:
        return self.test_status == "tested"


class CapabilityRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, CapabilityEntry] = {}

    def register(self, entry: CapabilityEntry) -> None:
        self._entries[entry.capability_id] = entry

    def get(self, capability_id: str) -> CapabilityEntry | None:
        return self._entries.get(capability_id)

    def all(self) -> list[CapabilityEntry]:
        return sorted(self._entries.values(), key=lambda entry: entry.capability_id)

    def match_domain(self, prompt: str) -> CapabilityEntry | None:
        lowered = prompt.lower()
        scored: list[tuple[int, CapabilityEntry]] = []
        for entry in self.all():
            score = sum(1 for term in entry.domain_terms if term.lower() in lowered)
            if score:
                scored.append((score, entry))
        if not scored:
            return None
        scored.sort(key=lambda item: (-item[0], item[1].capability_id))
        selectable = [entry for _, entry in scored if entry.is_selectable()]
        if selectable:
            return selectable[0]
        return scored[0][1]


FOUR_BAR_CAPABILITY = CapabilityEntry(
    capability_id="four_bar_linkage",
    version="0.1.0",
    domain="planar four-bar linkage mechanisms",
    input_schema="NormalizedBrief",
    output_schema="Candidate + GeometryArtifact (stl)",
    units="mm",
    parameter_constraints={
        "link lengths": "positive, at most 10000 mm",
        "input angles": "between -3600 and 3600 degrees",
    },
    evaluation_checks=(
        "travel_distance",
        "trajectory_tolerance",
        "max_footprint",
        "complete_motion_cycle",
        "avoid_collisions",
        "simulation_integrity",
    ),
    known_limitations=(
        "Links are zero-thickness line segments; the ground link is a fixed frame.",
        "Collision checks cover moving links only.",
        "No structural, fatigue, thermal or dynamic analysis is available.",
    ),
    resource_limits={
        "max_candidates": 3.0,
        "max_prompt_characters": 4000.0,
        "simulation_samples": 361.0,
    },
    test_status="tested",
    domain_terms=(
        "four-bar",
        "four bar",
        "fourbar",
        "linkage",
        "crank",
        "rocker",
        "coupler",
        "mechanism",
    ),
)


CUSTOM_PART_CAPABILITY = CapabilityEntry(
    capability_id="custom_part",
    version="0.1.0",
    domain="single static part or simplified representative geometry inside a bounding envelope",
    input_schema="PartBrief",
    output_schema="DesignProgram + GeometryArtifact (stl)",
    units="mm",
    parameter_constraints={
        "envelope": "positive dimensions, at most 10000 mm",
        "source": "CadQuery Python, 20000 characters maximum",
    },
    evaluation_checks=(
        "program_executed",
        "mesh_valid",
        "envelope_width",
        "envelope_height",
        "envelope_thickness",
        "determinism",
        "size_within_budget",
    ),
    known_limitations=(
        "Design programs run in a best-effort sandbox (import allowlist, curated builtins, "
        "resource limits); it is not a hardened OS boundary.",
        "Only static single-solid geometry is verified; no strength, thermal or dynamic analysis.",
        "Requests beyond a single part are reduced to simplified representative geometry; the "
        "full product, its mechanisms and its certifications are not modeled.",
        "Moving assemblies and multi-component products are not supported.",
    ),
    resource_limits={
        "max_program_seconds": 15.0,
        "max_export_bytes": 5_000_000.0,
    },
    test_status="tested",
    domain_terms=(
        "bracket",
        "plate",
        "clip",
        "holder",
        "adapter",
        "fixture",
        "spacer",
        "flange",
        "enclosure",
        "housing",
        "bushing",
        "standoff",
        "mounting plate",
    ),
)


ASSEMBLY_CAPABILITY = CapabilityEntry(
    capability_id="assembly",
    version="0.1.0",
    domain="small mechanical assembly of static solids with revolute joints inside an envelope",
    input_schema="PartBrief",
    output_schema="DesignProgram (assembly) + per-part GeometryArtifact (stl)",
    units="mm",
    parameter_constraints={
        "parts": "2 to 12",
        "joints": "at most 6 revolute joints",
        "envelope": "positive dimensions, at most 10000 mm",
    },
    evaluation_checks=(
        "program_executed",
        "mesh_valid",
        "parts_present",
        "joints_valid",
        "articulation_clearance",
        "envelope_width",
        "envelope_height",
        "envelope_thickness",
        "determinism",
        "size_within_budget",
    ),
    known_limitations=(
        "Design programs run in a best-effort sandbox (import allowlist, curated builtins, "
        "resource limits); it is not a hardened OS boundary.",
        "Only each joint's declared parent/child pair is checked for articulation interference; "
        "pins, bores and hardware clearances are not verified.",
        "Only static solid geometry is verified; no structural, thermal, dynamic or "
        "manufacturing analysis is performed.",
    ),
    resource_limits={
        "max_program_seconds": 15.0,
        "max_export_bytes": 5_000_000.0,
        "max_parts": 12.0,
        "max_joints": 6.0,
    },
    test_status="tested",
    domain_terms=(
        "hinge",
        "knuckle",
        "assembly",
        "assembled",
        "leaf",
        "leaves",
        "pivot",
        "articulat",
        "clevis",
        "hinge pin",
        "bracket assembly",
    ),
)


STRUCTURAL_CAPABILITY = CapabilityEntry(
    capability_id="structural_frame",
    version="0.1.0",
    domain="static structural frame or truss of multiple solid parts inside an envelope",
    input_schema="PartBrief",
    output_schema="DesignProgram (structure) + per-part GeometryArtifact (stl)",
    units="mm",
    parameter_constraints={
        "parts": "2 to 80",
        "envelope": "positive dimensions, at most 10000 mm",
    },
    evaluation_checks=(
        "program_executed",
        "mesh_valid",
        "envelope_width",
        "envelope_height",
        "envelope_thickness",
        "determinism",
        "size_within_budget",
        "parts_present",
        "span_matches_envelope",
    ),
    known_limitations=(
        "Design programs run in a best-effort sandbox (import allowlist, curated builtins, "
        "resource limits); it is not a hardened OS boundary.",
        "Only closed solid geometry, overall dimensions (5% envelope tolerance) and determinism "
        "are verified; no load, deflection, joint-strength or safety analysis is performed.",
        "Connection plates and bolt holes are geometry only; fasteners, material properties, "
        "tolerances and manufacturing are not modeled.",
    ),
    resource_limits={
        "max_program_seconds": 15.0,
        "max_export_bytes": 5_000_000.0,
        "max_parts": 80.0,
    },
    test_status="tested",
    domain_terms=(
        "truss",
        "bridge",
        "girder",
        "joist",
        "plank",
        "deck",
        "brace",
        "lattice",
        "strut",
        "beam",
        "column",
        "frame",
    ),
)


def default_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(FOUR_BAR_CAPABILITY)
    registry.register(CUSTOM_PART_CAPABILITY)
    registry.register(ASSEMBLY_CAPABILITY)
    registry.register(STRUCTURAL_CAPABILITY)
    return registry


__all__ = [
    "ASSEMBLY_CAPABILITY",
    "STRUCTURAL_CAPABILITY",
    "CUSTOM_PART_CAPABILITY",
    "CapabilityEntry",
    "CapabilityRegistry",
    "CapabilitySupport",
    "FOUR_BAR_CAPABILITY",
    "default_registry",
]
