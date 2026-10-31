from app.evaluation.evaluator import EVALUATOR_VERSION, evaluate_candidate
from app.mechanism.schemas import (
    CandidateMetrics,
    EvaluationStatus,
    HardConstraints,
    NormalizedBrief,
    TargetMotion,
)


def make_brief() -> NormalizedBrief:
    return NormalizedBrief.model_validate(
        {
            "mechanism_type": "four_bar_linkage",
            "units": "mm",
            "target_motion": {
                "type": "near_horizontal",
                "travel_distance": 100,
                "trajectory_tolerance": 5,
            },
            "constraints": {
                "max_footprint": 200,
                "complete_motion_cycle": True,
                "avoid_collisions": True,
            },
        }
    )


def make_metrics(**overrides: object) -> CandidateMetrics:
    values: dict[str, object] = {
        "travel_distance_mm": 100.0,
        "footprint_mm": 180.0,
        "trajectory_error_mm": 2.0,
        "cycle_completed": True,
        "collision_free": True,
        "simulation_valid": True,
    }
    values.update(overrides)
    return CandidateMetrics.model_validate(values)


def test_passing_metrics_produce_passed_evaluation() -> None:
    evaluation = evaluate_candidate(make_brief(), make_metrics(), "candidate_001")

    assert evaluation.status is EvaluationStatus.PASSED
    assert evaluation.failed_constraints == []
    assert evaluation.evaluator_version == EVALUATOR_VERSION


def test_evaluator_reports_every_failed_constraint() -> None:
    evaluation = evaluate_candidate(
        make_brief(),
        make_metrics(
            travel_distance_mm=120.0,
            footprint_mm=240.0,
            trajectory_error_mm=9.0,
            cycle_completed=False,
            collision_free=False,
            simulation_valid=False,
        ),
        "candidate_002",
    )

    assert evaluation.status is EvaluationStatus.FAILED
    assert evaluation.failed_constraints == [
        "travel_distance",
        "trajectory_tolerance",
        "max_footprint",
        "complete_motion_cycle",
        "avoid_collisions",
        "simulation_integrity",
    ]
    assert len(evaluation.diagnostic_notes) == 6


def test_travel_distance_uses_brief_tolerance() -> None:
    evaluation = evaluate_candidate(
        make_brief(),
        make_metrics(travel_distance_mm=104.9),
        "candidate_003",
    )
    assert evaluation.status is EvaluationStatus.PASSED

    evaluation = evaluate_candidate(
        make_brief(),
        make_metrics(travel_distance_mm=105.1),
        "candidate_004",
    )
    assert evaluation.failed_constraints == ["travel_distance"]


def test_same_inputs_are_deterministic() -> None:
    brief = make_brief()
    metrics = make_metrics(travel_distance_mm=94.0)

    first = evaluate_candidate(brief, metrics, "candidate_005")
    second = evaluate_candidate(brief, metrics, "candidate_005")

    assert first == second


def test_defaulted_motion_target_is_not_enforced() -> None:
    from app.mechanism.schemas import RequirementSource

    brief = NormalizedBrief(
        target_motion=TargetMotion(travel_distance=50.0, trajectory_tolerance=5.0),
        constraints=HardConstraints(max_footprint=100.0),
        requirement_sources={
            "target_motion": RequirementSource.DEFAULT_ASSUMPTION,
            "constraints.max_footprint": RequirementSource.DEFAULT_ASSUMPTION,
        },
    )
    metrics = CandidateMetrics(
        travel_distance_mm=80.78,
        footprint_mm=160.0,
        trajectory_error_mm=15.3,
        cycle_completed=True,
        collision_free=True,
        simulation_valid=True,
    )

    evaluation = evaluate_candidate(brief, metrics, "candidate_001")

    assert evaluation.status is EvaluationStatus.PASSED
    assert evaluation.failed_constraints == []
    assert any("not enforced" in note for note in evaluation.diagnostic_notes)


def test_stated_motion_target_is_enforced() -> None:
    from app.mechanism.schemas import RequirementSource

    brief = NormalizedBrief(
        target_motion=TargetMotion(travel_distance=50.0, trajectory_tolerance=5.0),
        constraints=HardConstraints(max_footprint=200.0),
        requirement_sources={
            "target_motion.travel_distance": RequirementSource.USER_PROVIDED,
        },
    )
    metrics = CandidateMetrics(
        travel_distance_mm=80.78,
        footprint_mm=160.0,
        trajectory_error_mm=4.0,
        cycle_completed=True,
        collision_free=True,
        simulation_valid=True,
    )

    evaluation = evaluate_candidate(brief, metrics, "candidate_001")

    assert evaluation.status is EvaluationStatus.FAILED
    assert "travel_distance" in evaluation.failed_constraints


def test_ai_proposed_motion_target_is_not_enforced() -> None:
    from app.mechanism.schemas import RequirementSource

    brief = NormalizedBrief(
        target_motion=TargetMotion(travel_distance=50.0, trajectory_tolerance=5.0),
        constraints=HardConstraints(max_footprint=10_000.0),
        requirement_sources={
            "target_motion.travel_distance": RequirementSource.AI_PROPOSED,
            "target_motion.trajectory_tolerance": RequirementSource.AI_PROPOSED,
            "constraints.max_footprint": RequirementSource.DEFAULT_ASSUMPTION,
        },
    )
    metrics = CandidateMetrics(
        travel_distance_mm=80.78,
        footprint_mm=160.0,
        trajectory_error_mm=15.3,
        cycle_completed=True,
        collision_free=True,
        simulation_valid=True,
    )

    evaluation = evaluate_candidate(brief, metrics, "candidate_001")

    assert evaluation.status is EvaluationStatus.PASSED
    assert evaluation.failed_constraints == []
