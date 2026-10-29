"""Tests for model-authored design programs: sandbox, evaluation and pipeline."""

import hashlib
from pathlib import Path
from typing import Any

import pytest
from app.ai.meta_client import ModelCompletion
from app.evaluation.part_evaluator import PART_EVALUATOR_VERSION, evaluate_part
from app.mechanism.schemas import (
    DesignProgram,
    DesignRunCreateRequest,
    ExpectedBoundingBox,
    PartBrief,
    PartRequirements,
)
from app.orchestration.design_run import DesignRunOrchestrator, EventBroker, RunStore
from app.persistence.artifacts import ArtifactStore
from app.programs.runner import (
    ProgramRejectedError,
    run_design_program,
    static_check,
)

pytest.importorskip("cadquery")

GOOD_PROGRAM = """import cadquery as cq


def build():
    plate = cq.Workplane("XY").box(60, 40, 6)
    hole = cq.Workplane("XY").cylinder(20, 3)
    return plate.cut(hole)
"""

BIG_PROGRAM = """import cadquery as cq


def build():
    return cq.Workplane("XY").box(120, 40, 6)
"""

BROKEN_PROGRAM = """import cadquery as cq


def build():
    raise ValueError("boom")
"""

FORBIDDEN_PROGRAM = """import os


def build():
    return os.getcwd()
"""

PART_PROMPT = "Design a mounting bracket for a 40 mm sensor, at most 80 x 60 x 8 mm."

BRIEF = PartBrief(
    part=PartRequirements(
        description="Sensor mounting bracket",
        max_width_mm=80.0,
        max_height_mm=60.0,
        max_thickness_mm=8.0,
    )
)


def program(source: str, program_id: str = "program_001") -> DesignProgram:
    return DesignProgram(
        program_id=program_id,
        source=source,
        expected_bbox=ExpectedBoundingBox(width_mm=60, height_mm=40, thickness_mm=6),
    )


class ScriptedClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.schema_names: list[str] = []

    @property
    def is_configured(self) -> bool:
        return True

    async def complete_json(self, **kwargs: Any) -> ModelCompletion:
        payload = self.payloads.pop(0)
        self.schema_names.append(kwargs["schema_name"])
        return ModelCompletion(
            payload=payload, model="scripted", latency_ms=1.0, usage={"total_tokens": 1}
        )

    async def aclose(self) -> None:
        return None


def part_brief_payload(
    *, supported: bool = True, unsupported: list[str] | None = None
) -> dict[str, Any]:
    return {
        "supported": supported,
        "reason": "" if supported else "a motorbike umbrella is not a single static part",
        "description": "Sensor mounting bracket",
        "max_width_mm": 80.0,
        "max_height_mm": 60.0,
        "max_thickness_mm": 8.0,
        "assumptions": ["Envelope inferred from the request."],
        "unsupported_requirements": unsupported or [],
        "unknowns": [],
        "clarification_questions": [],
        "requirement_sources": [],
    }


def program_payload(source: str, *, width: float = 60.0) -> dict[str, Any]:
    return {
        "language": "python",
        "entrypoint": "build",
        "source": source,
        "declared_parameters": [{"name": "width", "value": width}],
        "expected_bbox_mm": {"width_mm": width, "height_mm": 40.0, "thickness_mm": 6.0},
        "notes": [],
    }


def test_sandbox_executes_and_validates_a_program() -> None:
    first = run_design_program(program(GOOD_PROGRAM))
    second = run_design_program(program(GOOD_PROGRAM))

    assert first.status == "executed"
    assert first.stats is not None
    assert first.stats.width_mm == pytest.approx(60.0, abs=0.1)
    assert first.stats.thickness_mm == pytest.approx(6.0, abs=0.1)
    assert first.sha256 == second.sha256


@pytest.mark.parametrize(
    "source",
    [
        FORBIDDEN_PROGRAM,
        "def build():\n    return open('/etc/passwd').read()\n",
        "def build():\n    return eval('1')\n",
        "x = 1\n",
    ],
)
def test_sandbox_rejects_unsafe_or_invalid_programs(source: str) -> None:
    with pytest.raises(ProgramRejectedError):
        static_check(program(source))


def test_sandbox_reports_execution_failures() -> None:
    result = run_design_program(program(BROKEN_PROGRAM))

    assert result.status == "failed"
    assert result.error is not None and "boom" in result.error


def test_part_evaluator_passes_a_within_envelope_part() -> None:
    execution = run_design_program(program(GOOD_PROGRAM))
    evaluation = evaluate_part(
        BRIEF, execution, program_id="program_001", deterministic=True
    )

    assert evaluation.status.value == "passed"
    assert evaluation.failed_checks == []
    assert evaluation.evaluator_version == PART_EVALUATOR_VERSION


def test_part_evaluator_flags_envelope_violation_and_nondeterminism() -> None:
    execution = run_design_program(program(BIG_PROGRAM))
    evaluation = evaluate_part(
        BRIEF, execution, program_id="program_001", deterministic=False
    )

    assert evaluation.status.value == "failed"
    assert "envelope_width" in evaluation.failed_checks
    assert "determinism" in evaluation.failed_checks


def test_part_evaluator_fails_when_execution_fails() -> None:
    evaluation = evaluate_part(
        BRIEF, None, program_id="program_001", deterministic=None
    )

    assert evaluation.status.value == "failed"
    assert "program_executed" in evaluation.failed_checks


def make_orchestrator(tmp_path: Path, client: ScriptedClient) -> DesignRunOrchestrator:
    artifacts = ArtifactStore(tmp_path)
    return DesignRunOrchestrator(
        store=RunStore(artifacts),
        events=EventBroker(),
        artifacts=artifacts,
        meta_client=client,
    )


async def test_unmatched_prompt_falls_back_to_model_authored_capability(
    tmp_path: Path,
) -> None:
    client = ScriptedClient([part_brief_payload(), program_payload(GOOD_PROGRAM)])
    orchestrator = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(
        DesignRunCreateRequest(prompt="Design a wall hook, 40 x 30 x 10 mm.")
    )

    await orchestrator.execute(run.run_id)

    stored = orchestrator.store.get(run.run_id)
    assert stored is not None
    assert stored.capability_id == "custom_part"
    assert stored.no_pass is False


async def test_safety_critical_request_pauses_and_stays_partial(tmp_path: Path) -> None:
    client = ScriptedClient(
        [
            part_brief_payload(
                unsupported=["impact protection", "visor mechanism", "certification"]
            ),
            program_payload(GOOD_PROGRAM),
        ]
    )
    orchestrator = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(
        DesignRunCreateRequest(prompt="Design a motorcycle helmet shell.")
    )

    await orchestrator.execute(run.run_id)

    paused = orchestrator.store.get(run.run_id)
    assert paused is not None
    assert paused.status.value == "awaiting_clarification"
    assert any(
        question.field == "verification_scope.kinematic_only"
        for question in paused.pending_clarifications
    )

    orchestrator.submit_clarifications(run.run_id, {"verification_scope": "yes"})
    await orchestrator.execute(run.run_id)

    stored = orchestrator.store.get(run.run_id)
    assert stored is not None
    assert stored.status.value == "completed"
    assert stored.no_pass is False
    evidence = orchestrator.artifacts.read_json(run.run_id, "evidence.json")
    assessment = evidence["requirements"]["capability_assessment"]
    assert assessment["status"] == "partial"
    assert any("impact protection" in item for item in assessment["unsupported_requirements"])
    assert evidence["outcome"] == "passed"


async def test_part_pipeline_runs_the_model_program_and_passes(tmp_path: Path) -> None:
    client = ScriptedClient([part_brief_payload(), program_payload(GOOD_PROGRAM)])
    orchestrator = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PART_PROMPT))

    await orchestrator.execute(run.run_id)

    stored = orchestrator.store.get(run.run_id)
    assert stored is not None
    assert stored.status.value == "completed"
    assert stored.no_pass is False
    assert stored.capability_id == "custom_part"
    assert stored.final_candidate_id == "program_001"

    programs = orchestrator.artifacts.read_json(run.run_id, "programs.json")
    assert len(programs) == 1
    assert programs[0]["execution_status"] == "executed"
    assert programs[0]["evaluation"]["status"] == "passed"
    assert programs[0]["geometry_artifact_id"] == "geometry_program_001.stl"

    source_artifact = orchestrator.artifacts.read_bytes(run.run_id, "program_001.py")
    assert source_artifact is not None
    assert hashlib.sha256(source_artifact).hexdigest() == programs[0]["source_hash"]

    stl = orchestrator.artifacts.read_bytes(run.run_id, "geometry_program_001.stl")
    assert stl is not None
    evidence = orchestrator.artifacts.read_json(run.run_id, "evidence.json")
    assert evidence["outcome"] == "passed"
    assert evidence["programs"][0]["artifact_hash"] == hashlib.sha256(stl).hexdigest()
    assert evidence["programs"][0]["program"]["source"] == GOOD_PROGRAM


async def test_part_pipeline_repairs_a_failing_program(tmp_path: Path) -> None:
    client = ScriptedClient(
        [part_brief_payload(), program_payload(BROKEN_PROGRAM), program_payload(GOOD_PROGRAM)]
    )
    orchestrator = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PART_PROMPT))

    await orchestrator.execute(run.run_id)

    stored = orchestrator.store.get(run.run_id)
    assert stored is not None
    assert stored.no_pass is False
    assert stored.final_candidate_id == "program_002"
    programs = orchestrator.artifacts.read_json(run.run_id, "programs.json")
    assert [item["evaluation"]["status"] for item in programs] == ["failed", "passed"]


async def test_part_pipeline_reports_no_pass_honestly(tmp_path: Path) -> None:
    client = ScriptedClient(
        [
            part_brief_payload(),
            program_payload(BIG_PROGRAM),
            program_payload(BROKEN_PROGRAM),
        ]
    )
    orchestrator = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(
        DesignRunCreateRequest(prompt=PART_PROMPT, options={"max_candidates": 2})
    )

    await orchestrator.execute(run.run_id)

    stored = orchestrator.store.get(run.run_id)
    assert stored is not None
    assert stored.status.value == "completed"
    assert stored.no_pass is True
    evidence = orchestrator.artifacts.read_json(run.run_id, "evidence.json")
    assert evidence["outcome"] == "no_pass"


async def test_unsupported_part_request_stays_honest(tmp_path: Path) -> None:
    client = ScriptedClient([part_brief_payload(supported=False)])
    orchestrator = make_orchestrator(tmp_path, client)
    run = orchestrator.create_run(
        DesignRunCreateRequest(prompt="Design a mounting bracket for a whole motorbike.")
    )

    await orchestrator.execute(run.run_id)

    stored = orchestrator.store.get(run.run_id)
    assert stored is not None
    assert stored.status.value == "completed"
    assert stored.no_pass is True
    assert stored.final_candidate_id is None
    evidence = orchestrator.artifacts.read_json(run.run_id, "evidence.json")
    assert evidence["outcome"] == "not_supported"
    assert evidence["requirements"]["capability_assessment"]["status"] == "not_supported"


async def test_part_capability_requires_the_model_offline(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path)
    orchestrator = DesignRunOrchestrator(
        store=RunStore(artifacts), events=EventBroker(), artifacts=artifacts
    )
    run = orchestrator.create_run(DesignRunCreateRequest(prompt=PART_PROMPT))

    await orchestrator.execute(run.run_id)

    stored = orchestrator.store.get(run.run_id)
    assert stored is not None
    assert stored.no_pass is True
    evidence = orchestrator.artifacts.read_json(run.run_id, "evidence.json")
    assert evidence["outcome"] == "not_supported"
    assert "Meta model" in evidence["requirements"]["capability_assessment"][
        "unsupported_requirements"
    ][0]
