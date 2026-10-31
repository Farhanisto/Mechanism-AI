from app.mechanism.schemas import (
    CandidateMetrics,
    Evaluation,
    EvaluationStatus,
    NormalizedBrief,
    RequirementSource,
)

EVALUATOR_VERSION = "0.1.0"


def _requirement_is_stated(
    sources: dict[str, RequirementSource], prefix: str
) -> bool:
    """A target is enforced only when the user explicitly stated it.

    Model-proposed and defaulted values stay recorded as guidance/assumptions,
    not acceptance criteria. Briefs without provenance are treated as
    authoritative (backward compatible).
    """
    relevant = [
        source
        for field, source in sources.items()
        if field == prefix or field.startswith(f"{prefix}.")
    ]
    if not relevant:
        return True
    return any(source is RequirementSource.USER_PROVIDED for source in relevant)


def evaluate_candidate(
    brief: NormalizedBrief,
    metrics: CandidateMetrics,
    candidate_id: str,
) -> Evaluation:
    """Apply the brief's fixed acceptance criteria to measured metrics."""
    failed: list[str] = []
    notes: list[str] = []

    target_travel = brief.target_motion.travel_distance
    tolerance = brief.target_motion.trajectory_tolerance
    motion_stated = _requirement_is_stated(
        brief.requirement_sources, "target_motion"
    )
    footprint_stated = _requirement_is_stated(
        brief.requirement_sources, "constraints.max_footprint"
    )

    if motion_stated:
        travel_error = abs(metrics.travel_distance_mm - target_travel)
        if travel_error > tolerance:
            failed.append("travel_distance")
            notes.append(
                f"Travel distance {metrics.travel_distance_mm:.2f} mm misses "
                f"{target_travel:.2f} mm by {travel_error:.2f} mm "
                f"(tolerance {tolerance:.2f} mm)."
            )

        if metrics.trajectory_error_mm > tolerance:
            failed.append("trajectory_tolerance")
            notes.append(
                f"Trajectory error {metrics.trajectory_error_mm:.2f} mm exceeds "
                f"tolerance {tolerance:.2f} mm."
            )
    else:
        notes.append(
            "Travel and trajectory targets were default assumptions, not stated "
            "requirements; those checks are reported but not enforced."
        )

    if footprint_stated and metrics.footprint_mm > brief.constraints.max_footprint:
        failed.append("max_footprint")
        notes.append(
            f"Footprint {metrics.footprint_mm:.2f} mm exceeds the "
            f"{brief.constraints.max_footprint:.2f} mm limit."
        )

    if brief.constraints.complete_motion_cycle and not metrics.cycle_completed:
        failed.append("complete_motion_cycle")
        notes.append("The requested input cycle did not complete.")

    if brief.constraints.avoid_collisions and not metrics.collision_free:
        failed.append("avoid_collisions")
        notes.append("A prohibited collision was detected.")

    if not metrics.simulation_valid:
        failed.append("simulation_integrity")
        notes.append("The simulation produced invalid or non-finite results.")

    status = EvaluationStatus.FAILED if failed else EvaluationStatus.PASSED
    return Evaluation(
        candidate_id=candidate_id,
        status=status,
        metrics=metrics,
        failed_constraints=failed,
        evaluator_version=EVALUATOR_VERSION,
        diagnostic_notes=notes,
    )
