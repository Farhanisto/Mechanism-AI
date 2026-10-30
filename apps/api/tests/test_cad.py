"""Tests for the deterministic CAD compiler (skipped when CadQuery is absent)."""

import hashlib
import struct
from pathlib import Path

import pytest

pytest.importorskip("cadquery")

from app.ai.candidate_parser import default_candidate  # noqa: E402
from app.cad.compiler import (  # noqa: E402
    COMPILER_VERSION,
    compile_plan,
    mesh_stats,
)
from app.cad.plan import InvalidPlanError, plan_from_candidate  # noqa: E402
from app.mechanism.schemas import (  # noqa: E402
    DesignRunCreateRequest,
    FourBarParameters,
    PlanGeometryOp,
)
from app.orchestration.design_run import (  # noqa: E402
    DesignRunOrchestrator,
    EventBroker,
    RunStore,
)
from app.persistence.artifacts import ArtifactStore  # noqa: E402


def test_plan_from_candidate_is_deterministic() -> None:
    candidate = default_candidate(attempt_number=1)

    first = plan_from_candidate(candidate)
    second = plan_from_candidate(candidate)

    assert first == second
    assert first.capability_id == "four_bar_linkage"
    assert len(first.components) == 4
    assert len(first.joints) == 4
    assert {op.operation for op in first.geometry_operations} == {"extrude_link"}


def test_compile_is_deterministic_and_validates_geometry() -> None:
    plan = plan_from_candidate(default_candidate(attempt_number=1))

    first = compile_plan(plan, artifact_id="geometry_test.stl")
    second = compile_plan(plan, artifact_id="geometry_test.stl")

    assert first.data == second.data
    assert first.artifact.artifact_hash == second.artifact.artifact_hash
    assert first.artifact.generation_status == "generated"
    assert first.artifact.compiler_version == COMPILER_VERSION
    assert all(first.artifact.validation_results.values())

    triangle_count = struct.unpack_from("<I", first.data, 80)[0]
    assert triangle_count > 0
    assert len(first.data) == 84 + triangle_count * 50


def test_unsupported_operation_is_rejected() -> None:
    plan = plan_from_candidate(default_candidate(attempt_number=1))
    tampered = plan.model_copy(
        update={"geometry_operations": [PlanGeometryOp(operation="shell")]}
    )

    with pytest.raises(InvalidPlanError, match="unsupported geometry operation"):
        compile_plan(tampered, artifact_id="geometry_bad.stl")


def test_operation_referencing_unknown_component_is_rejected() -> None:
    plan = plan_from_candidate(default_candidate(attempt_number=1))
    tampered = plan.model_copy(
        update={
            "geometry_operations": [
                PlanGeometryOp(operation="extrude_link", component_id="missing")
            ]
        }
    )

    with pytest.raises(InvalidPlanError, match="unknown component"):
        compile_plan(tampered, artifact_id="geometry_bad.stl")


def test_invalid_parameters_are_rejected() -> None:
    plan = plan_from_candidate(default_candidate(attempt_number=1))
    component = plan.components[0]
    tampered = plan.model_copy(
        update={
            "components": [
                component.model_copy(
                    update={"parameters": {**component.parameters, "length": -5.0}}
                ),
                *plan.components[1:],
            ]
        }
    )

    with pytest.raises(InvalidPlanError):
        compile_plan(tampered, artifact_id="geometry_bad.stl")


def test_geometry_inconsistent_with_length_is_rejected() -> None:
    plan = plan_from_candidate(default_candidate(attempt_number=1))
    component = plan.components[0]
    shifted = {
        **component.parameters,
        "end_x": component.parameters["end_x"] + 20.0,
    }
    tampered = plan.model_copy(
        update={
            "components": [
                component.model_copy(update={"parameters": shifted}),
                *plan.components[1:],
            ]
        }
    )

    with pytest.raises(InvalidPlanError, match="does not match its length"):
        compile_plan(tampered, artifact_id="geometry_bad.stl")


def test_unassemblable_candidate_is_rejected() -> None:
    candidate = default_candidate(attempt_number=1).model_copy(
        update={
            "parameters": FourBarParameters(
                ground_length=1000.0,
                crank_length=10.0,
                coupler_length=10.0,
                rocker_length=10.0,
            )
        }
    )

    with pytest.raises(InvalidPlanError, match="cannot be assembled"):
        plan_from_candidate(candidate)


def test_plan_honors_component_specs_and_adds_pins() -> None:
    plan = plan_from_candidate(
        default_candidate(attempt_number=1),
        link_thickness_mm=6.0,
        pivot_hole_mm=8.0,
        include_pins=True,
    )

    kinds = [component.kind for component in plan.components]
    assert kinds.count("link") == 4
    assert kinds.count("pin") == 4
    assert all(
        component.parameters["thickness"] == 6.0
        and component.parameters["pin_hole_diameter"] == 8.0
        for component in plan.components
        if component.kind == "link"
    )

    compiled = compile_plan(plan, artifact_id="geometry_specs.stl")
    assert compiled.artifact.generation_status == "generated"
    stats = mesh_stats(compiled.data)
    # 6 mm plates plus 12 mm pins protruding through them.
    assert stats.thickness_mm == pytest.approx(12.0, abs=0.2)
    repeated = compile_plan(plan, artifact_id="geometry_specs.stl")
    assert repeated.data == compiled.data


async def test_pipeline_writes_the_geometry_artifact(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path)
    orchestrator = DesignRunOrchestrator(
        store=RunStore(artifacts), events=EventBroker(), artifacts=artifacts
    )
    run = orchestrator.create_run(
        DesignRunCreateRequest(
            prompt="Design a four-bar linkage with 100 mm of travel in a 200 mm footprint."
        )
    )

    await orchestrator.execute(run.run_id)

    candidates = orchestrator.store.list_candidates(run.run_id)
    artifact_id = candidates[0].candidate.geometry_artifact_id
    assert artifact_id == "geometry_candidate_001.stl"

    data = artifacts.read_bytes(run.run_id, artifact_id)
    assert data is not None
    entry = next(
        entry for entry in artifacts.manifest(run.run_id) if entry.name == artifact_id
    )
    assert entry.sha256 == hashlib.sha256(data).hexdigest()

    evidence = artifacts.read_json(run.run_id, "evidence.json")
    geometry = evidence["geometry_artifacts"][0]
    assert geometry["generation_status"] == "generated"
    assert geometry["artifact_hash"] == entry.sha256
    assert geometry["compiler_version"] == COMPILER_VERSION
