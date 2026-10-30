"""Tests for the structural_frame capability (static truss/frame geometry)."""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("cadquery")

from app.ai.meta_client import ModelCompletion  # noqa: E402
from app.capabilities.registry import default_registry  # noqa: E402
from app.evaluation.part_evaluator import evaluate_part  # noqa: E402
from app.mechanism.schemas import (  # noqa: E402
    DesignProgram,
    DesignRunCreateRequest,
    ExpectedBoundingBox,
    PartBrief,
    PartRequirements,
)
from app.orchestration.design_run import (  # noqa: E402
    DesignRunOrchestrator,
    EventBroker,
    RunStore,
)
from app.persistence.artifacts import ArtifactStore  # noqa: E402
from app.programs.runner import run_design_program  # noqa: E402

BRIDGE_PROMPT = (
    "Design a wooden truss bridge with a 900 mm length and 180 mm width. Include two side "
    "trusses made from rectangular wooden beams, diagonal braces, vertical supports, and a "
    "wooden deck made from evenly spaced planks. Add connection plates and bolt holes at the "
    "joints. Assemble all components into a 3D model."
)

TRUSS_PROGRAM = """import cadquery as cq


def build():
    parts = {}
    parts["deck"] = cq.Workplane("XY").box(900, 180, 8)
    for side, label in ((-1, "left"), (1, "right")):
        y = side * 80
        parts[f"top_chord_{label}"] = (
            cq.Workplane("XY").box(900, 10, 12).translate((0, y, 120))
        )
        parts[f"bottom_chord_{label}"] = (
            cq.Workplane("XY").box(900, 10, 12).translate((0, y, 12))
        )
        for index in range(6):
            x = -350 + index * 140
            parts[f"vertical_{label}_{index}"] = (
                cq.Workplane("XY").box(10, 10, 100).translate((x, y, 66))
            )
    return {"parts": parts}
"""

TINY_PROGRAM = """import cadquery as cq


def build():
    parts = {}
    for index in range(4):
        parts[f"block_{index}"] = (
            cq.Workplane("XY").box(10, 10, 10).translate((index * 12, 0, 0))
        )
    return {"parts": parts}
"""

BRIEF = PartBrief(
    part=PartRequirements(
        description="Wooden truss bridge",
        max_width_mm=900.0,
        max_height_mm=180.0,
        max_thickness_mm=200.0,
    )
)


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


def brief_payload() -> dict[str, Any]:
    return {
        "supported": True,
        "reason": "",
        "description": "Wooden truss bridge with deck, chords, verticals and braces",
        "max_width_mm": 900.0,
        "max_height_mm": 180.0,
        "max_thickness_mm": 200.0,
        "assumptions": [],
        "unknowns": [],
        "unsupported_requirements": ["load capacity", "deflection"],
        "clarification_questions": [],
        "requirement_sources": [],
    }


def program_payload(source: str) -> dict[str, Any]:
    return {
        "language": "python",
        "entrypoint": "build",
        "source": source,
        "declared_parameters": [{"name": "span", "value": 900.0}],
        "expected_bbox_mm": {"width_mm": 900.0, "height_mm": 180.0, "thickness_mm": 130.0},
        "notes": [],
    }


def execution(source: str):
    return run_design_program(
        DesignProgram(
            program_id="program_001",
            capability_id="structural_frame",
            source=source,
            expected_bbox=ExpectedBoundingBox(
                width_mm=900, height_mm=180, thickness_mm=200
            ),
        )
    )


def test_bridge_prompt_routes_to_the_structural_capability() -> None:
    registry = default_registry()

    assert registry.match_domain(BRIDGE_PROMPT).capability_id == "structural_frame"
    assert registry.match_domain("Model a hinge with leaves and a pin.").capability_id == "assembly"
    assert (
        registry.match_domain("Design a four-bar linkage with 100 mm travel").capability_id
        == "four_bar_linkage"
    )


def test_structure_program_exports_many_parts_without_joints() -> None:
    result = execution(TRUSS_PROGRAM)

    assert result.status == "executed"
    assert len(result.parts) == 17
    assert result.joints == ()


def test_structure_evaluator_passes_a_spanning_frame() -> None:
    evaluation = evaluate_part(
        BRIEF,
        execution(TRUSS_PROGRAM),
        program_id="program_001",
        deterministic=True,
        require_structure=True,
    )

    assert evaluation.status.value == "passed", evaluation.diagnostic_notes
    assert evaluation.metrics.part_count == 17


def test_structure_evaluator_rejects_a_tiny_model() -> None:
    evaluation = evaluate_part(
        BRIEF,
        execution(TINY_PROGRAM),
        program_id="program_001",
        deterministic=True,
        require_structure=True,
    )

    assert evaluation.status.value == "failed"
    assert "span_matches_envelope" in evaluation.failed_checks
    assert any("requested span" in note for note in evaluation.diagnostic_notes)


def test_structure_evaluator_does_not_require_joints() -> None:
    result = execution(TRUSS_PROGRAM)
    evaluation = evaluate_part(
        BRIEF, result, program_id="program_001", deterministic=True, require_structure=True
    )

    assert "joints_valid" not in evaluation.failed_checks
    assert "articulation_clearance" not in evaluation.failed_checks


async def test_structure_pipeline_runs_the_model_program(tmp_path: Path) -> None:
    client = ScriptedClient([brief_payload(), program_payload(TRUSS_PROGRAM)])
    artifacts = ArtifactStore(tmp_path)
    orchestrator = DesignRunOrchestrator(
        store=RunStore(artifacts),
        events=EventBroker(),
        artifacts=artifacts,
        meta_client=client,
    )
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=BRIDGE_PROMPT))

    await orchestrator.execute(run.run_id)

    stored = orchestrator.store.get(run.run_id)
    assert stored is not None
    assert stored.capability_id == "structural_frame"
    assert stored.status.value == "completed"
    assert stored.no_pass is False
    assert client.schema_names == ["part_brief", "design_program"]

    programs = orchestrator.artifacts.read_json(run.run_id, "programs.json")
    record = programs[0]
    assert record["evaluation"]["status"] == "passed"
    assert len(record["parts"]) == 17
    assert record["joints"] == []
    for part in record["parts"]:
        assert orchestrator.artifacts.read_bytes(run.run_id, part["artifact_id"])

    evidence = orchestrator.artifacts.read_json(run.run_id, "evidence.json")
    assert evidence["requirements"]["capability_assessment"]["capability_id"] == (
        "structural_frame"
    )
    assert evidence["requirements"]["capability_assessment"]["status"] == "partial"
    assert any(
        "no load, deflection" in limitation for limitation in evidence["limitations"]
    )
    assert any(
        "load capacity" in item
        for item in evidence["requirements"]["capability_assessment"][
            "unsupported_requirements"
        ]
    )
