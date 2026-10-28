"""Contract tests for the typed design, geometry and evidence objects."""

import json
from datetime import UTC, datetime

import pytest
from app.mechanism.schemas import (
    ArtifactManifestEntry,
    CandidateRecord,
    CapabilityAssessment,
    CapabilitySupport,
    ClarificationQuestion,
    DesignPlan,
    DesignRun,
    DesignRunCreateRequest,
    Evaluation,
    EvaluationStatus,
    EvidenceBundle,
    GeometryArtifact,
    HardConstraints,
    NormalizedBrief,
    PlanComponent,
    PlanGeometryOp,
    PlanJoint,
    PreviewMode,
    RequirementSource,
    SimulationEngineInfo,
    SimulationResult,
    TargetMotion,
    Units,
    UserMode,
)
from pydantic import ValidationError


def make_brief() -> NormalizedBrief:
    return NormalizedBrief(
        target_motion=TargetMotion(travel_distance=100.0, trajectory_tolerance=5.0),
        constraints=HardConstraints(max_footprint=200.0),
        assumptions=["Rocker pin is the output point."],
        unknowns=["operating temperature"],
        clarification_questions=[
            ClarificationQuestion(
                question_id="q1",
                question="What temperature will it operate at?",
                field="operating_temperature",
                blocking=True,
            )
        ],
        requirement_sources={
            "target_motion.travel_distance": RequirementSource.USER_PROVIDED,
            "constraints.max_footprint": RequirementSource.AI_PROPOSED,
            "output_point": RequirementSource.DEFAULT_ASSUMPTION,
        },
        capability_assessment=CapabilityAssessment(
            capability_id="four_bar_linkage",
            capability_version="0.1.0",
            status=CapabilitySupport.SUPPORTED,
        ),
    )


def make_run() -> DesignRun:
    now = datetime.now(UTC)
    return DesignRun(
        run_id="run_contract",
        status="completed",
        stage="completed",
        original_prompt="Design a four-bar linkage.",
        created_at=now,
        updated_at=now,
    )


def test_design_run_request_contract() -> None:
    request = DesignRunCreateRequest(
        prompt="Design a four-bar linkage.",
        user_mode=UserMode.EXPERT,
        preview_modes=[PreviewMode.CAD, PreviewMode.MOTION],
        units=Units.MM,
    )

    assert request.user_mode is UserMode.EXPERT
    assert request.preview_modes == [PreviewMode.CAD, PreviewMode.MOTION]
    assert request.options.max_candidates == 3

    with pytest.raises(ValidationError):
        DesignRunCreateRequest(prompt="x", unknown_field=True)


def test_requirements_brief_contract_carries_provenance_and_questions() -> None:
    brief = make_brief()

    assert brief.unknowns == ["operating temperature"]
    assert brief.clarification_questions[0].blocking is True
    assert brief.requirement_sources["output_point"] is RequirementSource.DEFAULT_ASSUMPTION
    assert brief.capability_assessment is not None
    assert brief.capability_assessment.status is CapabilitySupport.SUPPORTED

    with pytest.raises(ValidationError):
        NormalizedBrief(
            target_motion=TargetMotion(travel_distance=100.0),
            constraints=HardConstraints(max_footprint=200.0),
            surprise=True,
        )


def test_design_plan_contract() -> None:
    plan = DesignPlan(
        capability_id="four_bar_linkage",
        capability_version="0.1.0",
        components=[
            PlanComponent(component_id="crank", kind="link", parameters={"length": 35.0})
        ],
        joints=[
            PlanJoint(
                joint_id="crank_hinge",
                kind="revolute",
                parent="ground",
                child="crank",
                limits_deg=(-180.0, 180.0),
            )
        ],
        geometry_operations=[PlanGeometryOp(operation="extrude", component_id="crank")],
        required_checks=["travel_distance", "avoid_collisions"],
        resource_budget={"max_solver_iterations": 100},
    )

    assert json.loads(plan.model_dump_json())["components"][0]["parameters"]["length"] == 35.0

    with pytest.raises(ValidationError):
        PlanJoint(joint_id="j", kind="weld", parent="a", child="b")


def test_geometry_artifact_contract() -> None:
    artifact = GeometryArtifact(
        artifact_id="geom_001",
        format="step",
        compiler_version="0.1.0",
        generation_status="generated",
        validation_results={"is_manifold": True},
        artifact_hash="abc123",
    )

    assert artifact.units is Units.MM
    assert artifact.error is None

    with pytest.raises(ValidationError):
        GeometryArtifact(
            artifact_id="geom_002",
            format="iges",
            compiler_version="0.1.0",
            generation_status="generated",
        )


def test_candidate_carries_geometry_reference() -> None:
    record = CandidateRecord.model_validate(
        {
            "candidate": {
                "candidate_id": "candidate_001",
                "mechanism_type": "four_bar_linkage",
                "parameters": {
                    "ground_length": 95.0,
                    "crank_length": 35.0,
                    "coupler_length": 135.0,
                    "rocker_length": 100.0,
                },
                "input_motion": {"start_angle_deg": 0.0, "end_angle_deg": 360.0},
                "generated_at": datetime.now(UTC).isoformat(),
                "attempt_number": 1,
                "geometry_artifact_id": "geom_001",
            },
            "evaluation": None,
        }
    )

    assert record.candidate.geometry_artifact_id == "geom_001"


def test_simulation_result_contract_includes_warnings() -> None:
    result = SimulationResult(
        candidate_id="candidate_001",
        engine="mujoco",
        engine_version="3.17.0",
        warnings=["settle steps reached the cap at 12 degrees"],
    )

    assert result.warnings == ["settle steps reached the cap at 12 degrees"]
    assert result.time_basis == "normalized_cycle"


def test_evidence_bundle_round_trips_through_json() -> None:
    evaluation = Evaluation(
        candidate_id="candidate_001",
        status=EvaluationStatus.PASSED,
        metrics={
            "travel_distance_mm": 99.5,
            "footprint_mm": 182.0,
            "trajectory_error_mm": 4.1,
            "cycle_completed": True,
            "collision_free": True,
            "simulation_valid": True,
        },
        failed_constraints=[],
        evaluator_version="0.1.0",
    )
    record = CandidateRecord.model_validate(
        {
            "candidate": {
                "candidate_id": "candidate_001",
                "mechanism_type": "four_bar_linkage",
                "parameters": {
                    "ground_length": 95.0,
                    "crank_length": 35.0,
                    "coupler_length": 135.0,
                    "rocker_length": 100.0,
                },
                "input_motion": {"start_angle_deg": 0.0, "end_angle_deg": 360.0},
                "generated_at": datetime.now(UTC).isoformat(),
                "attempt_number": 1,
            },
            "evaluation": evaluation.model_dump(mode="json"),
        }
    )
    bundle = EvidenceBundle(
        run=make_run(),
        prompt="Design a four-bar linkage.",
        requirements={
            "source": "deterministic_fallback",
            "brief": make_brief().model_dump(mode="json"),
        },
        simulation_engine=SimulationEngineInfo(name="mujoco", version="3.17.0"),
        limits={"max_candidates": 3},
        collision_model="moving_links_only_zero_thickness",
        evaluator_version="0.1.0",
        candidates=[record],
        final_candidate_id="candidate_001",
        no_pass=False,
        outcome="passed",
        limitations=["Passing checks certify kinematic criteria only."],
        manifest=[
            ArtifactManifestEntry(
                name="run.json",
                sha256="a" * 64,
                size_bytes=123,
                written_at=datetime.now(UTC).isoformat(),
            )
        ],
    )

    restored = EvidenceBundle.model_validate(json.loads(bundle.model_dump_json()))

    assert restored == bundle
    assert restored.candidates[0].evaluation is not None
    assert restored.manifest[0].name == "run.json"
