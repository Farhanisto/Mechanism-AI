"""Benchmark suites for the independent evaluator and the bounded repair loop.

The fixtures live in ``apps/api/benchmarks`` and carry manually reviewed
expected outcomes. Recorded results and assumptions are documented in
``apps/api/benchmarks/README.md``.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.ai.meta_client import ModelCompletion
from app.evaluation.evaluator import evaluate_candidate
from app.evaluation.metrics import measure_simulation
from app.mechanism.schemas import (
    Candidate,
    DesignRunCreateRequest,
    FourBarParameters,
    HardConstraints,
    InputMotion,
    MechanismType,
    NormalizedBrief,
    TargetMotion,
)
from app.orchestration.design_run import DesignRunOrchestrator, EventBroker, RunStore
from app.persistence.artifacts import ArtifactStore
from app.simulation.runner import run_candidate_simulation

_BENCHMARKS = Path(__file__).resolve().parents[1] / "benchmarks"
_EVALUATOR_CASES = json.loads(
    (_BENCHMARKS / "evaluator_benchmark.json").read_text()
)["cases"]
_REPAIR_CASES = json.loads((_BENCHMARKS / "repair_benchmark.json").read_text())["cases"]
_GENERATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _brief(spec: dict[str, Any]) -> NormalizedBrief:
    return NormalizedBrief(
        target_motion=TargetMotion.model_validate(spec["target_motion"]),
        constraints=HardConstraints.model_validate(spec["constraints"]),
    )


def _candidate(case: dict[str, Any]) -> Candidate:
    return Candidate(
        candidate_id="benchmark_case",
        mechanism_type=MechanismType.FOUR_BAR_LINKAGE,
        parameters=FourBarParameters.model_validate(case["parameters"]),
        input_motion=InputMotion.model_validate(case["input_motion"]),
        generated_at=_GENERATED_AT,
        attempt_number=1,
    )


class _ScriptedClient:
    def __init__(
        self,
        brief_payload: dict[str, Any],
        candidate_payloads: list[dict[str, Any]],
    ) -> None:
        self._brief_payload = brief_payload
        self._candidate_payloads = list(candidate_payloads)

    @property
    def is_configured(self) -> bool:
        return True

    async def complete_json(self, **kwargs: Any) -> ModelCompletion:
        if kwargs["schema_name"] == "normalized_brief":
            payload = self._brief_payload
        else:
            payload = self._candidate_payloads.pop(0)
        return ModelCompletion(
            payload=payload,
            model="benchmark-scripted",
            latency_ms=1.0,
            usage={"total_tokens": 1},
        )

    async def aclose(self) -> None:
        return None


def _sequence_payloads(case: dict[str, Any]) -> list[dict[str, Any]]:
    payloads = []
    for item in case["candidate_sequence"]:
        if "parameters" not in item:
            payloads.append(item)
            continue
        payloads.append(
            {
                "mechanism_type": "four_bar_linkage",
                "parameters": item["parameters"],
                "input_motion": item["input_motion"],
            }
        )
    return payloads


@pytest.mark.parametrize("case", _EVALUATOR_CASES, ids=lambda case: case["id"])
def test_evaluator_benchmark_classification(case: dict[str, Any]) -> None:
    simulation = run_candidate_simulation(_candidate(case))
    metrics = measure_simulation(simulation)
    evaluation = evaluate_candidate(_brief(case["brief"]), metrics, "benchmark_case")

    assert evaluation.status.value == case["expected"]["status"]
    assert evaluation.failed_constraints == case["expected"]["failed_constraints"]


def test_evaluator_benchmark_contains_all_case_categories() -> None:
    categories = {case["category"] for case in _EVALUATOR_CASES}

    assert {"passing", "failing", "boundary", "invalid"} <= categories
    assert any(case["expected"]["status"] == "passed" for case in _EVALUATOR_CASES)
    assert any(case["expected"]["status"] == "failed" for case in _EVALUATOR_CASES)


@pytest.mark.parametrize("case", _REPAIR_CASES, ids=lambda case: case["id"])
async def test_repair_benchmark(case: dict[str, Any], tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path)
    orchestrator = DesignRunOrchestrator(
        store=RunStore(artifacts),
        events=EventBroker(),
        artifacts=artifacts,
        meta_client=_ScriptedClient(
            brief_payload={
                "target_motion": case["brief"]["target_motion"],
                "constraints": case["brief"]["constraints"],
                "assumptions": [],
            },
            candidate_payloads=_sequence_payloads(case),
        ),
    )
    run = orchestrator.create_run(
        DesignRunCreateRequest(prompt="benchmark repair case", options={"max_candidates": 3})
    )
    await orchestrator.execute(run.run_id)

    stored_run = orchestrator.store.get(run.run_id)
    assert stored_run is not None
    expected = case["expected"]
    if expected["outcome"] == "run_failed":
        assert stored_run.status.value == "failed"
        assert stored_run.error_code == expected["error_code"]
        return

    assert stored_run.status.value == "completed"
    assert stored_run.no_pass is (expected["outcome"] == "no_pass")
    assert stored_run.final_candidate_id == expected["final_candidate_id"]
    candidates = orchestrator.store.list_candidates(run.run_id)
    assert len(candidates) == expected["attempts_used"]
    assert all(record.evaluation is not None for record in candidates)


async def test_repair_benchmark_success_rate(tmp_path: Path) -> None:
    repairable = [case for case in _REPAIR_CASES if case["category"] == "repairable"]
    succeeded = 0
    for case in repairable:
        artifacts = ArtifactStore(tmp_path / case["id"])
        orchestrator = DesignRunOrchestrator(
            store=RunStore(artifacts),
            events=EventBroker(),
            artifacts=artifacts,
            meta_client=_ScriptedClient(
                brief_payload={
                    "target_motion": case["brief"]["target_motion"],
                    "constraints": case["brief"]["constraints"],
                    "assumptions": [],
                },
                candidate_payloads=_sequence_payloads(case),
            ),
        )
        run = orchestrator.create_run(
            DesignRunCreateRequest(
                prompt="benchmark repair case", options={"max_candidates": 3}
            )
        )
        await orchestrator.execute(run.run_id)
        stored_run = orchestrator.store.get(run.run_id)
        if (
            stored_run is not None
            and stored_run.status.value == "completed"
            and stored_run.no_pass is False
        ):
            succeeded += 1

    assert repairable, "the repair benchmark must contain repairable cases"
    success_rate = succeeded / len(repairable)
    assert success_rate >= 0.7
