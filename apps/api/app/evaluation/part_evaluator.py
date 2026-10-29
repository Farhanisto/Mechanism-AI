"""Independent evaluator for model-authored geometry.

Fixed checks over the executed artifacts: for single solids the program must
run, the mesh must be valid, the envelope must match the brief, the program must
be deterministic and the export must stay within budget. For assemblies the
parts and joints must exist and the jointed parts must move through the declared
range without interpenetrating. Thresholds live here, not in model output.
"""

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
SIZE_BUDGET_BYTES = 5_000_000
ARTICULATION_ANGLES = 3

CHECKS = (
    "program_executed",
    "mesh_valid",
    "envelope_width",
    "envelope_height",
    "envelope_thickness",
    "determinism",
    "size_within_budget",
)
ASSEMBLY_CHECKS = (
    "parts_present",
    "joints_valid",
    "articulation_clearance",
)


def evaluate_part(
    brief: PartBrief,
    execution: ProgramExecution | None,
    *,
    program_id: str,
    deterministic: bool | None,
    require_assembly: bool = False,
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

    if stats is not None:
        for name, actual, limit in (
            ("width", stats.width_mm, brief.part.max_width_mm),
            ("height", stats.height_mm, brief.part.max_height_mm),
            ("thickness", stats.thickness_mm, brief.part.max_thickness_mm),
        ):
            within = actual <= limit + ENVELOPE_TOLERANCE_MM
            checks[f"envelope_{name}"] = within
            if not within:
                allowance = limit + ENVELOPE_TOLERANCE_MM
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
                and joint.min_deg <= joint.max_deg
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
        if not checks["parts_present"]:
            notes.append("An assembly needs at least two parts.")
        if not checks["joints_valid"]:
            notes.append("An assembly needs at least one valid revolute joint.")

    ordered = list(CHECKS)
    if require_assembly:
        ordered.extend(ASSEMBLY_CHECKS)
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
    "ASSEMBLY_CHECKS",
    "CHECKS",
    "ENVELOPE_TOLERANCE_MM",
    "PART_EVALUATOR_VERSION",
    "SIZE_BUDGET_BYTES",
    "evaluate_part",
]
