"""Independent evaluator for model-authored part geometry.

Fixed checks over the executed artifact: the program must run, the mesh must be
valid, the bounding envelope must match the brief, the program must be
deterministic and the export must stay within budget. Thresholds live here, not
in model output.
"""

from app.mechanism.schemas import (
    EvaluationStatus,
    PartBrief,
    PartEvaluation,
    PartMetrics,
)
from app.programs.runner import ProgramExecution

PART_EVALUATOR_VERSION = "0.1.0"
ENVELOPE_TOLERANCE_MM = 0.5
SIZE_BUDGET_BYTES = 5_000_000

CHECKS = (
    "program_executed",
    "mesh_valid",
    "envelope_width",
    "envelope_height",
    "envelope_thickness",
    "determinism",
    "size_within_budget",
)


def evaluate_part(
    brief: PartBrief,
    execution: ProgramExecution | None,
    *,
    program_id: str,
    deterministic: bool | None,
) -> PartEvaluation:
    notes: list[str] = []
    checks: dict[str, bool] = {}

    executed = execution is not None and execution.status == "executed"
    stats = execution.stats if executed else None
    checks["program_executed"] = bool(executed and stats is not None)
    if execution is not None and execution.error:
        notes.append(f"Program execution: {execution.error}")

    checks["mesh_valid"] = bool(
        stats is not None and stats.triangle_count > 0 and stats.volume_mm3 > 0.0
    )

    if stats is not None:
        width_limit = brief.part.max_width_mm
        height_limit = brief.part.max_height_mm
        thickness_limit = brief.part.max_thickness_mm
        for name, actual, limit in (
            ("width", stats.width_mm, width_limit),
            ("height", stats.height_mm, height_limit),
            ("thickness", stats.thickness_mm, thickness_limit),
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

    failed = [name for name in CHECKS if not checks.get(name, False)]
    metrics = PartMetrics(
        width_mm=stats.width_mm if stats else 0.0,
        height_mm=stats.height_mm if stats else 0.0,
        thickness_mm=stats.thickness_mm if stats else 0.0,
        volume_mm3=stats.volume_mm3 if stats else 0.0,
        triangle_count=stats.triangle_count if stats else 0,
        deterministic=checks["determinism"],
        mesh_valid=checks["mesh_valid"],
        program_status=execution.status if execution is not None else "rejected",
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
    "CHECKS",
    "ENVELOPE_TOLERANCE_MM",
    "PART_EVALUATOR_VERSION",
    "SIZE_BUDGET_BYTES",
    "evaluate_part",
]
