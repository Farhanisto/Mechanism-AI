"""Tests for model-authored assemblies: parts, joints and articulation checks."""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("cadquery")

from app.ai.meta_client import ModelCompletion
from app.capabilities.registry import default_registry
from app.evaluation.part_evaluator import evaluate_part
from app.mechanism.schemas import (
    DesignRunCreateRequest,
    PartBrief,
    PartRequirements,
)
from app.orchestration.design_run import DesignRunOrchestrator, EventBroker, RunStore
from app.persistence.artifacts import ArtifactStore
from app.programs.meshes import meshes_interfere
from app.programs.runner import run_design_program

HINGE_PROMPT = (
    "Model a hinge with two rectangular leaves, each 50 x 30 x 3 mm, three interlocking "
    "cylindrical knuckles, and a 6 mm diameter hinge pin. Assemble it so the leaves can "
    "rotate relative to one another."
)

CLEAR_HINGE = """import cadquery as cq


def build():
    leaf_a = cq.Workplane("XY").box(50, 30, 3).translate((0, 18, 0))
    leaf_b = cq.Workplane("XY").box(50, 30, 3).translate((0, -18, 0))
    pin = cq.Workplane("YZ").cylinder(56, 2.5).translate((-24, 0, 0))
    return {
        "parts": {
            "leaf_a": leaf_a,
            "leaf_b": leaf_b,
            "pin": pin,
        },
        "joints": [
            {
                "name": "hinge",
                "parent": "leaf_a",
                "child": "leaf_b",
                "origin": [0, 0, 0],
                "axis": [1, 0, 0],
                "min_deg": -90,
                "max_deg": 90,
            }
        ],
    }
"""

COLLIDING_HINGE = """import cadquery as cq


def build():
    leaf_a = cq.Workplane("XY").box(50, 30, 3).translate((0, 15, 0))
    leaf_b = cq.Workplane("XY").box(50, 30, 3).translate((0, -15, 0))
    return {
        "parts": {"leaf_a": leaf_a, "leaf_b": leaf_b},
        "joints": [
            {
                "name": "hinge",
                "parent": "leaf_a",
                "child": "leaf_b",
                "origin": [0, 0, 0],
                "axis": [1, 0, 0],
                "min_deg": -90,
                "max_deg": 90,
            }
        ],
    }
"""

BRIEF = PartBrief(
    part=PartRequirements(
        description="Hinge assembly",
        max_width_mm=90.0,
        max_height_mm=90.0,
        max_thickness_mm=12.0,
    )
)

CLASSES = ("app.programs.runner.ProgramRejectedError",)


def program_payload(source: str) -> dict[str, Any]:
    return {
        "language": "python",
        "entrypoint": "build",
        "source": source,
        "declared_parameters": [{"name": "leaf_length", "value": 50.0}],
        "expected_bbox_mm": {"width_mm": 50.0, "height_mm": 60.0, "thickness_mm": 8.0},
        "notes": [],
    }


def brief_payload() -> dict[str, Any]:
    return {
        "supported": True,
        "reason": "",
        "description": "Hinge assembly with two leaves and a pin",
        "max_width_mm": 90.0,
        "max_height_mm": 90.0,
        "max_thickness_mm": 12.0,
        "assumptions": [],
        "unknowns": [],
        "unsupported_requirements": [],
        "clarification_questions": [],
        "requirement_sources": [],
    }


class ScriptedClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.schema_names: list[str] = []

    @property
    def is_configured(self) -> bool:
        return True

    async def complete_json(self, **kwargs: Any) -> ModelCompletion:
        self.schema_names.append(kwargs["schema_name"])
        return ModelCompletion(
            payload=self.payloads.pop(0),
            model="scripted",
            latency_ms=1.0,
            usage={"total_tokens": 1},
        )

    async def aclose(self) -> None:
        return None


COMPONENT_LINKAGE_PROMPT = (
    "Build a four-bar linkage using four separate components: ground link (120 mm), "
    "crank (40 mm), coupler (100 mm), and rocker (90 mm). Make each link 6 mm thick "
    "with 8 mm pivot holes. Add cylindrical pins and assemble all components using "
    "revolute joints. Keep the ground link fixed."
)


def test_hinge_prompt_routes_to_the_assembly_capability() -> None:
    registry = default_registry()

    assert registry.match_domain(HINGE_PROMPT).capability_id == "assembly"
    assert (
        registry.match_domain("Design a four-bar linkage with 100 mm travel").capability_id
        == "four_bar_linkage"
    )


def test_component_linkage_prompt_stays_on_the_four_bar_capability() -> None:
    registry = default_registry()

    # A four-bar linkage request keeps the four-bar capability (and its kinematic
    # evaluation) even when it asks for separate components, pins and joints.
    assert registry.match_domain(COMPONENT_LINKAGE_PROMPT).capability_id == "four_bar_linkage"


def test_sandbox_exports_assembly_parts_and_joints() -> None:
    program = __import__("app.mechanism.schemas", fromlist=["DesignProgram"]).DesignProgram(
        program_id="program_001",
        source=CLEAR_HINGE,
        expected_bbox=__import__(
            "app.mechanism.schemas", fromlist=["ExpectedBoundingBox"]
        ).ExpectedBoundingBox(width_mm=50.0, height_mm=60.0, thickness_mm=8.0),
    )

    execution = run_design_program(program)

    assert execution.status == "executed"
    assert {part.name for part in execution.parts} == {"leaf_a", "leaf_b", "pin"}
    assert len(execution.joints) == 1
    assert execution.joints[0].parent == "leaf_a"
    assert all(part.stats.volume_mm3 > 0 for part in execution.parts)


def test_interference_detects_overlap_but_not_touching() -> None:
    from app.mechanism.schemas import DesignProgram, ExpectedBoundingBox

    def part_source(offset: float) -> str:
        return f"""import cadquery as cq


def build():
    return cq.Workplane("XY").box(50, 30, 3).translate(({offset}, 0, 0))
"""

    def build(offset: float) -> Any:
        return run_design_program(
            DesignProgram(
                program_id="program_001",
                source=part_source(offset),
                expected_bbox=ExpectedBoundingBox(
                    width_mm=50, height_mm=30, thickness_mm=3
                ),
            )
        )

    base = build(0.0)
    overlap = build(10.0)
    apart = build(100.0)

    assert meshes_interfere(base.stl, overlap.stl) is True
    assert meshes_interfere(base.stl, apart.stl) is False


def test_assembly_evaluator_passes_clear_articulation() -> None:
    from app.mechanism.schemas import DesignProgram, ExpectedBoundingBox

    program = DesignProgram(
        program_id="program_001",
        source=CLEAR_HINGE,
        expected_bbox=ExpectedBoundingBox(width_mm=50, height_mm=60, thickness_mm=8),
    )
    execution = run_design_program(program)

    evaluation = evaluate_part(
        BRIEF, execution, program_id="program_001", deterministic=True, require_assembly=True
    )

    assert evaluation.status.value == "passed", evaluation.diagnostic_notes
    assert evaluation.metrics.part_count == 3
    assert evaluation.metrics.joint_count == 1


def test_assembly_evaluator_flags_colliding_articulation() -> None:
    from app.mechanism.schemas import DesignProgram, ExpectedBoundingBox

    program = DesignProgram(
        program_id="program_001",
        source=COLLIDING_HINGE,
        expected_bbox=ExpectedBoundingBox(width_mm=50, height_mm=60, thickness_mm=3),
    )
    execution = run_design_program(program)

    evaluation = evaluate_part(
        BRIEF, execution, program_id="program_001", deterministic=True, require_assembly=True
    )

    assert evaluation.status.value == "failed"
    assert "articulation_clearance" in evaluation.failed_checks
    assert any("overlap" in note for note in evaluation.diagnostic_notes)


def test_assembly_requires_two_parts_and_a_joint() -> None:
    from app.mechanism.schemas import DesignProgram, ExpectedBoundingBox

    single = DesignProgram(
        program_id="program_001",
        source="""import cadquery as cq


def build():
    return cq.Workplane("XY").box(20, 20, 5)
""",
        expected_bbox=ExpectedBoundingBox(width_mm=20, height_mm=20, thickness_mm=5),
    )
    execution = run_design_program(single)

    evaluation = evaluate_part(
        PartBrief(
            part=PartRequirements(
                description="single",
                max_width_mm=90,
                max_height_mm=90,
                max_thickness_mm=12,
            )
        ),
        execution,
        program_id="program_001",
        deterministic=True,
        require_assembly=True,
    )

    assert evaluation.status.value == "failed"
    assert "parts_present" in evaluation.failed_checks
    assert "joints_valid" in evaluation.failed_checks


def make_orchestrator(tmp_path: Path, client: ScriptedClient) -> DesignRunOrchestrator:
    artifacts = ArtifactStore(tmp_path)
    return DesignRunOrchestrator(
        store=RunStore(artifacts),
        events=EventBroker(),
        artifacts=artifacts,
        meta_client=client,
    )


async def test_assembly_pipeline_runs_the_model_program(tmp_path: Path) -> None:
    client = ScriptedClient([brief_payload(), program_payload(CLEAR_HINGE)])
    orchestrator = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=HINGE_PROMPT))

    await orchestrator.execute(run.run_id)

    stored = orchestrator.store.get(run.run_id)
    assert stored is not None
    assert stored.capability_id == "assembly"
    assert stored.status.value == "completed"
    assert stored.no_pass is False
    assert client.schema_names == ["part_brief", "design_program"]

    programs = orchestrator.artifacts.read_json(run.run_id, "programs.json")
    assert len(programs) == 1
    record = programs[0]
    assert record["evaluation"]["status"] == "passed"
    assert {part["name"] for part in record["parts"]} == {"leaf_a", "leaf_b", "pin"}
    assert record["joints"][0]["parent"] == "leaf_a"

    for part in record["parts"]:
        data = orchestrator.artifacts.read_bytes(run.run_id, part["artifact_id"])
        assert data is not None

    evidence = orchestrator.artifacts.read_json(run.run_id, "evidence.json")
    assert evidence["outcome"] == "passed"
    assert evidence["requirements"]["capability_assessment"]["capability_id"] == "assembly"
    assert any(
        "articulation" in limitation for limitation in evidence["limitations"]
    )
