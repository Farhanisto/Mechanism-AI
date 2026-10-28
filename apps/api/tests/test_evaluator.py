from app.evaluation.evaluator import EVALUATOR_VERSION, evaluate_candidate
from app.mechanism.schemas import (
    CandidateMetrics,
    EvaluationStatus,
    NormalizedBrief,
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
