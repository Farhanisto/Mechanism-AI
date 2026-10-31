"""Independent evaluator for model-authored geometry.

Fixed checks over the executed artifacts: for single solids the program must
run, the mesh must be valid, the envelope must match the brief, the program must
be deterministic and the export must stay within budget. For assemblies the
parts and joints must exist and the jointed parts must move through the declared
range without interpenetrating. Thresholds live here, not in model output.
"""

import re

from app.mechanism.schemas import (
    EvaluationStatus,
    PartBrief,
    PartEvaluation,
    PartMetrics,
)
from app.programs.meshes import articulation_clearance
from app.programs.runner import ProgramExecution

PART_EVALUATOR_VERSION = "0.2.0"
ENVELOPE_TOLERANCE_MM = 0.5
SIZE_BUDGET_BYTES = 20_000_000
ARTICULATION_ANGLES = 3

CHECKS = (
    "program_executed",
    "mesh_valid",
    "components_covered",
    "envelope_width",
    "envelope_height",
    "envelope_thickness",
    "determinism",
    "size_within_budget",
)
ASSEMBLY_CHECKS = (
    "parts_present",
    "joints_valid",
    "motion_covered",
    "articulation_clearance",
)
STRUCTURE_CHECKS = (
    "parts_present",
    "span_matches_envelope",
)
SCOPE_CHECKS = ("single_part_scope",)
MIN_STRUCTURE_PARTS = 4
SPAN_TOLERANCE_RATIO = 0.9
STRUCTURE_ENVELOPE_TOLERANCE_RATIO = 0.05


def _tokens(text: str) -> set[str]:
    tokens = {
        token for token in re.split(r"[^a-z0-9]+", text.lower()) if len(token) >= 3
    }
    stop_words = {
        "the",
        "and",
        "with",
        "part",
        "parts",
        "for",
        "into",
        "from",
        "that",
        "this",
    }
    return {
        (token[:-1] if token.endswith("s") and len(token) > 3 else token)
        for token in tokens
        if token not in stop_words
    }


def _missing_components(required: list[str], part_names: list[str]) -> list[str]:
    part_tokens: set[str] = set()
    for name in part_names:
        part_tokens |= _tokens(name)
    missing: list[str] = []
    for requirement in required:
        tokens = _tokens(requirement)
        if tokens and not (tokens & part_tokens):
            missing.append(requirement)
    return missing


def evaluate_part(
    brief: PartBrief,
    execution: ProgramExecution | None,
    *,
    program_id: str,
    deterministic: bool | None,
    require_assembly: bool = False,
    require_structure: bool = False,
) -> PartEvaluation:
    notes: list[str] = []
    checks: dict[str, bool] = {}

    executed = execution is not None and execution.status == "executed"
    stats = execution.stats if executed else None
    parts = execution.parts if executed else ()
    checks["program_executed"] = bool(executed and stats is not None)
    if execution is not None and execution.error:
        notes.append(f"Program execution: {execution.error}")

    checks["mesh_valid"] = bool(parts) and all(
        part.stats.triangle_count > 0 and part.stats.volume_mm3 > 0.0 for part in parts
    )

    if require_assembly or require_structure:
        missing_components = _missing_components(
            brief.required_components, [part.name for part in parts]
        )
        checks["components_covered"] = executed and not missing_components
        if missing_components:
            notes.append(
                "The design does not include the requested components: "
                + ", ".join(missing_components)
            )

    if stats is not None:
        ratio = STRUCTURE_ENVELOPE_TOLERANCE_RATIO if require_structure else 0.0
        for name, actual, limit in (
            ("width", stats.width_mm, brief.part.max_width_mm),
            ("height", stats.height_mm, brief.part.max_height_mm),
            ("thickness", stats.thickness_mm, brief.part.max_thickness_mm),
        ):
            within = actual <= limit * (1.0 + ratio) + ENVELOPE_TOLERANCE_MM
            checks[f"envelope_{name}"] = within
            if not within:
                allowance = limit * (1.0 + ratio) + ENVELOPE_TOLERANCE_MM
                notes.append(
                    f"Measured {name} {actual:.2f} mm exceeds the {limit:.2f} mm "
                    f"envelope ({allowance:.2f} mm including tolerance)."
                )
    else:
        checks["envelope_width"] = False
        checks["envelope_height"] = False
        checks["envelope_thickness"] = False

    checks["determinism"] = bool(deterministic) if executed else False
    if executed and deterministic is False:
        notes.append(
            "Two executions of the same program produced different meshes; the design is "
            "not deterministic."
        )

    checks["size_within_budget"] = bool(
        execution is not None
        and execution.stl is not None
        and len(execution.stl) <= SIZE_BUDGET_BYTES
    )

    if require_assembly:
        checks["parts_present"] = bool(executed and len(parts) >= 2)
        valid_joints = bool(executed and execution.joints)
        if valid_joints:
            part_names = {part.name for part in parts}
            valid_joints = all(
                joint.parent in part_names
                and joint.child in part_names
                and joint.parent != joint.child
                and joint.min_value <= joint.max_value
                for joint in execution.joints
            )
        checks["joints_valid"] = valid_joints

        clearance_ok = False
        if valid_joints and executed:
            part_meshes = {part.name: part.stl for part in parts}
            clearance_ok = True
            for joint in execution.joints:
                ok, joint_notes = articulation_clearance(
                    part_meshes, joint.model_dump()
                )
                if not ok:
                    clearance_ok = False
                    notes.extend(
                        f"Joint '{joint.name}': {note}" for note in joint_notes
                    )
        checks["articulation_clearance"] = clearance_ok

        required_motion = brief.required_motion
        if required_motion == "prismatic":
            checks["motion_covered"] = any(
                joint.kind == "prismatic" for joint in execution.joints
            )
        elif required_motion == "rotary":
            checks["motion_covered"] = any(
                joint.kind == "revolute" for joint in execution.joints
            )
        else:
            checks["motion_covered"] = True
        if not checks["motion_covered"]:
            notes.append(
                f"The requested {required_motion} motion is not represented by the "
                "declared joints."
            )

        if not checks["parts_present"]:
            notes.append("An assembly needs at least two parts.")
        if not checks["joints_valid"]:
            notes.append("An assembly needs at least one valid joint.")

    if require_structure:
        checks["parts_present"] = bool(executed and len(parts) >= MIN_STRUCTURE_PARTS)
        if stats is not None:
            envelope_max = max(
                brief.part.max_width_mm,
                brief.part.max_height_mm,
                brief.part.max_thickness_mm,
            )
            measured_max = max(stats.width_mm, stats.height_mm, stats.thickness_mm)
            checks["span_matches_envelope"] = (
                measured_max >= envelope_max * SPAN_TOLERANCE_RATIO
            )
        else:
            checks["span_matches_envelope"] = False
        if not checks["parts_present"]:
            notes.append(
                f"A structural frame needs at least {MIN_STRUCTURE_PARTS} parts."
            )
        if not checks["span_matches_envelope"]:
            notes.append(
                "The structure is much smaller than the requested envelope; model it at "
                "the requested span/length."
            )

    if not require_assembly and not require_structure:
        # Features of one solid (bores, ribs, fillets) are not separate components; only
        # relative motion means the request does not fit a single static part.
        scope_ok = brief.required_motion == "none"
        checks["single_part_scope"] = scope_ok
        if not scope_ok:
            notes.append(
                "The request needs multiple parts or relative motion; the custom_part "
                "capability models one static part. Use the assembly capability."
            )

    ordered = list(CHECKS)
    if require_assembly:
        ordered.extend(ASSEMBLY_CHECKS)
    if require_structure:
        ordered.extend(STRUCTURE_CHECKS)
    if not require_assembly and not require_structure:
        # Component coverage applies to assemblies/structures; a single part's features
        # (bores, holes, ribs, fillets) live inside that one part.
        ordered = [name for name in ordered if name != "components_covered"]
        ordered.extend(SCOPE_CHECKS)
    failed = [name for name in ordered if not checks.get(name, False)]

    total_volume = sum(part.stats.volume_mm3 for part in parts)
    metrics = PartMetrics(
        width_mm=stats.width_mm if stats else 0.0,
        height_mm=stats.height_mm if stats else 0.0,
        thickness_mm=stats.thickness_mm if stats else 0.0,
        volume_mm3=total_volume if parts else 0.0,
        triangle_count=sum(part.stats.triangle_count for part in parts),
        deterministic=checks["determinism"],
        mesh_valid=checks["mesh_valid"],
        program_status=execution.status if execution is not None else "rejected",
        part_count=len(parts),
        joint_count=len(execution.joints) if execution is not None else 0,
    )
    return PartEvaluation(
        program_id=program_id,
        status=EvaluationStatus.FAILED if failed else EvaluationStatus.PASSED,
        metrics=metrics,
        failed_checks=failed,
        evaluator_version=PART_EVALUATOR_VERSION,
        diagnostic_notes=notes,
    )


__all__ = [
    "ARTICULATION_ANGLES",
    "SCOPE_CHECKS",
    "STRUCTURE_ENVELOPE_TOLERANCE_RATIO",
    "MIN_STRUCTURE_PARTS",
    "SPAN_TOLERANCE_RATIO",
    "STRUCTURE_CHECKS",
    "ASSEMBLY_CHECKS",
    "CHECKS",
    "ENVELOPE_TOLERANCE_MM",
    "PART_EVALUATOR_VERSION",
    "SIZE_BUDGET_BYTES",
    "evaluate_part",
]
