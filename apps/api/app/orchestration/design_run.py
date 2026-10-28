import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.ai.candidate_parser import default_candidate, generate_candidate
from app.ai.meta_client import (
    MetaModelClient,
    MetaModelError,
    ModelCompletion,
    UnconfiguredMetaModelClient,
)
from app.ai.requirements_parser import default_brief_from_prompt, parse_requirements
from app.evaluation.evaluator import EVALUATOR_VERSION, evaluate_candidate
from app.evaluation.metrics import measure_simulation
from app.mechanism.kinematics import DEFAULT_SAMPLE_COUNT, KinematicsError
from app.mechanism.schemas import (
    TERMINAL_EVENTS,
    CandidateRecord,
    DesignRun,
    DesignRunCreateRequest,
    EvaluationStatus,
    NormalizedBrief,
    RunEventName,
    RunStatus,
    Stage,
)
from app.persistence.artifacts import ArtifactStore
from app.simulation.mujoco_runner import SimulationNotAvailable
from app.simulation.runner import ENGINE_AUTO, run_candidate_simulation

logger = logging.getLogger(__name__)

_KEEPALIVE_SECONDS = 15.0
_TERMINAL_EVENT_NAMES = frozenset(name.value for name in TERMINAL_EVENTS)


@dataclass(frozen=True)
class RunEvent:
    event: str
    data: dict[str, Any]

    def to_sse(self) -> str:
        payload = json.dumps(self.data, separators=(",", ":"))
        return f"event: {self.event}\ndata: {payload}\n\n"


class EventBroker:
    def __init__(self) -> None:
        self._history: dict[str, list[RunEvent]] = defaultdict(list)
        self._subscribers: dict[str, list[asyncio.Queue[RunEvent | None]]] = defaultdict(list)

    def publish(self, run_id: str, event: str, data: dict[str, Any]) -> None:
        payload = RunEvent(
            event=event,
            data={
                "run_id": run_id,
                "ts": datetime.now(UTC).isoformat(),
                **data,
            },
        )
        self._history[run_id].append(payload)
        for queue in self._subscribers[run_id]:
            queue.put_nowait(payload)

    async def stream(self, run_id: str) -> AsyncIterator[RunEvent | None]:
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        self._subscribers[run_id].append(queue)
        try:
            for event in list(self._history[run_id]):
                yield event
                if event.event in _TERMINAL_EVENT_NAMES:
                    return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield None
                    continue
                yield event
                if event.event in _TERMINAL_EVENT_NAMES:
                    return
        finally:
            self._subscribers[run_id].remove(queue)
            if not self._subscribers[run_id]:
                del self._subscribers[run_id]


class RunStore:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self._artifacts = artifacts
        self._runs: dict[str, DesignRun] = {}
        self._candidates: dict[str, list[CandidateRecord]] = defaultdict(list)

    def create(self, run: DesignRun) -> DesignRun:
        self._runs[run.run_id] = run
        self._persist(run.run_id)
        return run

    def get(self, run_id: str) -> DesignRun | None:
        return self._runs.get(run_id)

    def update(self, run: DesignRun) -> DesignRun:
        self._runs[run.run_id] = run
        self._persist(run.run_id)
        return run

    def list_candidates(self, run_id: str) -> list[CandidateRecord]:
        return list(self._candidates[run_id])

    def add_candidate(self, run_id: str, record: CandidateRecord) -> CandidateRecord:
        self._candidates[run_id].append(record)
        self._persist_candidates(run_id)
        return record

    def _persist(self, run_id: str) -> None:
        self._artifacts.write_json(run_id, "run.json", self._runs[run_id])

    def _persist_candidates(self, run_id: str) -> None:
        records = [record.model_dump(mode="json") for record in self._candidates[run_id]]
        self._artifacts.write_json(run_id, "candidates.json", records)


class DesignRunOrchestrator:
    def __init__(
        self,
        *,
        store: RunStore,
        events: EventBroker,
        artifacts: ArtifactStore,
        meta_client: MetaModelClient | None = None,
        max_candidates: int = 3,
        max_run_seconds: float = 60.0,
        simulation_engine: str = ENGINE_AUTO,
        limits: dict[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.events = events
        self.artifacts = artifacts
        self.meta_client = meta_client or UnconfiguredMetaModelClient()
        self.max_candidates = max_candidates
        self.max_run_seconds = max_run_seconds
        self.simulation_engine = simulation_engine
        self.limits = limits or {}

    def create_run(self, payload: DesignRunCreateRequest) -> DesignRun:
        now = datetime.now(UTC)
        run = DesignRun(
            run_id=f"run_{uuid4().hex[:12]}",
            status=RunStatus.QUEUED,
            stage=Stage.QUEUED,
            original_prompt=payload.prompt,
            created_at=now,
            updated_at=now,
            max_candidates=min(payload.options.max_candidates, self.max_candidates),
        )
        return self.store.create(run)

    async def execute(self, run_id: str) -> None:
        run = self.store.get(run_id)
        if run is None:
            return
        self._update_run(run, status=RunStatus.RUNNING, stage=Stage.PARSE_REQUIREMENTS)
        self.events.publish(
            run_id,
            RunEventName.RUN_STARTED.value,
            {
                "status": run.status.value,
                "stage": run.stage.value,
                "max_candidates": run.max_candidates,
                "ai_enabled": self.meta_client.is_configured,
            },
        )
        try:
            async with asyncio.timeout(self.max_run_seconds):
                await self._run_pipeline(run)
        except TimeoutError:
            self._fail(
                run,
                "RUN_TIMEOUT",
                f"The design run exceeded its {self.max_run_seconds:.0f} second budget.",
            )
        except MetaModelError as exc:
            self._fail(run, exc.error_code, str(exc))
        except ValidationError:
            logger.exception("Model output failed schema validation for run %s", run_id)
            self._fail(
                run,
                "INVALID_MODEL_OUTPUT",
                "The model output did not match the required schema.",
            )
        except KinematicsError as exc:
            self._fail(run, "SIMULATION_ERROR", str(exc))
        except SimulationNotAvailable as exc:
            self._fail(run, "SIMULATION_UNAVAILABLE", str(exc))
        except Exception:
            logger.exception("Design run %s failed unexpectedly", run_id)
            self._fail(run, "INTERNAL_ERROR", "The design run failed unexpectedly.")

    async def _run_pipeline(self, run: DesignRun) -> None:
        provider_calls: list[dict[str, Any]] = []
        engine_info: dict[str, Any] = {
            "name": "not_run",
            "version": None,
            "time_basis": "normalized_cycle",
            "output_point": "rocker_pin",
        }
        source = "meta_model" if self.meta_client.is_configured else "deterministic_fallback"

        if self.meta_client.is_configured:
            brief, completion = await parse_requirements(
                run.original_prompt,
                client=self.meta_client,
            )
            self._record_completion(provider_calls, "requirements", completion)
        else:
            brief = default_brief_from_prompt(run.original_prompt)

        self.artifacts.write_json(
            run.run_id,
            "brief.json",
            {"source": source, "brief": brief.model_dump(mode="json")},
        )
        self.events.publish(
            run.run_id,
            RunEventName.REQUIREMENTS_PARSED.value,
            {
                "source": source,
                "mechanism_type": brief.mechanism_type.value,
                "target_motion": brief.target_motion.model_dump(mode="json"),
                "constraints": brief.constraints.model_dump(mode="json"),
                "assumptions": brief.assumptions,
            },
        )

        records: list[CandidateRecord] = []
        previous: CandidateRecord | None = None
        passed_record: CandidateRecord | None = None

        for attempt in range(1, run.max_candidates + 1):
            self._update_run(run, stage=Stage.GENERATE_CANDIDATE)
            if self.meta_client.is_configured:
                candidate, completion = await generate_candidate(
                    brief,
                    client=self.meta_client,
                    attempt_number=attempt,
                    max_attempts=run.max_candidates,
                    previous_candidate=previous.candidate if previous else None,
                    previous_evaluation=previous.evaluation if previous else None,
                )
                self._record_completion(provider_calls, f"candidate_{attempt:03d}", completion)
            else:
                candidate = default_candidate(attempt_number=attempt)

            self.events.publish(
                run.run_id,
                RunEventName.CANDIDATE_GENERATED.value,
                {
                    "candidate_id": candidate.candidate_id,
                    "attempt_number": candidate.attempt_number,
                    "source": source,
                    "parameters": candidate.parameters.model_dump(mode="json"),
                },
            )

            self._update_run(run, stage=Stage.SIMULATE)
            simulation = run_candidate_simulation(
                candidate, engine=self.simulation_engine
            )
            if engine_info["name"] == "not_run":
                engine_info = {
                    "name": simulation.engine,
                    "version": simulation.engine_version,
                    "time_basis": simulation.time_basis,
                    "output_point": "rocker_pin",
                }
                if simulation.diagnostics is not None:
                    engine_info["settings"] = simulation.diagnostics.model_dump(
                        mode="json", exclude={"reference_comparison"}
                    )
            self.artifacts.write_json(
                run.run_id,
                f"simulation_{candidate.candidate_id}.json",
                simulation,
            )
            self.events.publish(
                run.run_id,
                RunEventName.SIMULATION_COMPLETED.value,
                {
                    "candidate_id": candidate.candidate_id,
                    "engine": simulation.engine,
                    "engine_version": simulation.engine_version,
                    "sample_count": len(simulation.samples),
                    "cycle_completed": simulation.cycle_completed,
                    "collision_free": simulation.collision_free,
                    "simulation_valid": simulation.simulation_valid,
                    "failure_reason": simulation.failure_reason,
                },
            )

            self._update_run(run, stage=Stage.EVALUATE)
            metrics = measure_simulation(simulation)
            evaluation = evaluate_candidate(brief, metrics, candidate.candidate_id)
            record = CandidateRecord(candidate=candidate, evaluation=evaluation)
            self.store.add_candidate(run.run_id, record)
            records.append(record)
            self.events.publish(
                run.run_id,
                RunEventName.EVALUATION_COMPLETED.value,
                {
                    "candidate_id": candidate.candidate_id,
                    "status": evaluation.status.value,
                    "metrics": evaluation.metrics.model_dump(mode="json"),
                    "failed_constraints": evaluation.failed_constraints,
                    "diagnostic_notes": evaluation.diagnostic_notes,
                },
            )
            previous = record

            if evaluation.status is EvaluationStatus.PASSED:
                passed_record = record
                break

            if attempt < run.max_candidates:
                self._update_run(run, stage=Stage.REPAIR)
                self.events.publish(
                    run.run_id,
                    RunEventName.REPAIR_STARTED.value,
                    {
                        "candidate_id": candidate.candidate_id,
                        "next_attempt": attempt + 1,
                        "failed_constraints": evaluation.failed_constraints,
                    },
                )

        if not records:
            raise RuntimeError("The pipeline produced no candidate to evaluate.")
        final_record = passed_record or self._best_record(records, brief)
        no_pass = final_record.evaluation is None or (
            final_record.evaluation.status is not EvaluationStatus.PASSED
        )

        self._update_run(run, stage=Stage.REPORT)
        self._update_run(
            run,
            status=RunStatus.COMPLETED,
            stage=Stage.COMPLETED,
            final_candidate_id=final_record.candidate.candidate_id,
            no_pass=no_pass,
        )
        self.artifacts.write_json(
            run.run_id,
            "evidence.json",
            {
                "run": run.model_dump(mode="json"),
                "prompt": run.original_prompt,
                "requirements": {
                    "source": source,
                    "brief": brief.model_dump(mode="json"),
                },
                "simulation_engine": engine_info,
                "limits": {
                    "max_candidates": run.max_candidates,
                    "max_run_seconds": self.max_run_seconds,
                    "simulation_sample_count": DEFAULT_SAMPLE_COUNT,
                    **self.limits,
                },
                "collision_model": "moving_links_only_zero_thickness",
                "evaluator_version": EVALUATOR_VERSION,
                "provider_calls": provider_calls,
                "candidates": [
                    record.model_dump(mode="json") for record in records
                ],
                "final_candidate_id": final_record.candidate.candidate_id,
                "no_pass": no_pass,
            },
        )
        self.events.publish(
            run.run_id,
            RunEventName.RUN_COMPLETED.value,
            {
                "status": "no_pass" if no_pass else "passed",
                "stage": run.stage.value,
                "final_candidate_id": final_record.candidate.candidate_id,
                "failed_constraints": (
                    final_record.evaluation.failed_constraints
                    if final_record.evaluation is not None
                    else []
                ),
                "no_pass": no_pass,
            },
        )

    @staticmethod
    def _record_completion(
        provider_calls: list[dict[str, Any]],
        stage: str,
        completion: ModelCompletion,
    ) -> None:
        provider_calls.append(
            {
                "stage": stage,
                "model": completion.model,
                "latency_ms": round(completion.latency_ms, 2),
                "usage": completion.usage,
            }
        )

    @staticmethod
    def _best_record(
        records: list[CandidateRecord],
        brief: NormalizedBrief,
    ) -> CandidateRecord:
        target_travel = brief.target_motion.travel_distance
        max_footprint = brief.constraints.max_footprint

        def score(record: CandidateRecord) -> tuple[int, float]:
            evaluation = record.evaluation
            if evaluation is None:
                return (100, float("inf"))
            metrics = evaluation.metrics
            travel_error = abs(metrics.travel_distance_mm - target_travel)
            footprint_excess = max(0.0, metrics.footprint_mm - max_footprint)
            return (
                len(evaluation.failed_constraints),
                travel_error + metrics.trajectory_error_mm + footprint_excess,
            )

        return min(records, key=score)

    def _update_run(
        self,
        run: DesignRun,
        *,
        status: RunStatus | None = None,
        stage: Stage | None = None,
        error_code: str | None = None,
        final_candidate_id: str | None = None,
        no_pass: bool | None = None,
    ) -> DesignRun:
        if status is not None:
            run.status = status
        if stage is not None:
            run.stage = stage
        if error_code is not None:
            run.error_code = error_code
        if final_candidate_id is not None:
            run.final_candidate_id = final_candidate_id
        if no_pass is not None:
            run.no_pass = no_pass
        run.updated_at = datetime.now(UTC)
        return self.store.update(run)

    def _fail(self, run: DesignRun, error_code: str, message: str) -> None:
        self._update_run(run, status=RunStatus.FAILED, stage=Stage.FAILED, error_code=error_code)
        try:
            self.artifacts.write_json(
                run.run_id,
                "error.json",
                {
                    "error_code": error_code,
                    "message": message,
                    "ts": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            logger.exception("Could not persist the error artifact for run %s", run.run_id)
        self.events.publish(
            run.run_id,
            RunEventName.RUN_FAILED.value,
            {
                "status": run.status.value,
                "stage": run.stage.value,
                "error_code": error_code,
                "message": message,
            },
        )
