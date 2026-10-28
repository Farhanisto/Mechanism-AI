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
from app.capabilities.registry import CapabilityRegistry, default_registry
from app.capabilities.router import route_request
from app.evaluation.evaluator import EVALUATOR_VERSION, evaluate_candidate
from app.evaluation.metrics import measure_simulation
from app.mechanism.kinematics import DEFAULT_SAMPLE_COUNT, KinematicsError
from app.mechanism.schemas import (
    TERMINAL_EVENTS,
    CandidateRecord,
    CapabilityAssessment,
    CapabilitySupport,
    ClarificationQuestion,
    DesignRun,
    DesignRunCreateRequest,
    EvaluationStatus,
    EvidenceBundle,
    NormalizedBrief,
    RequirementSource,
    RunEventName,
    RunStatus,
    SimulationEngineInfo,
    Stage,
)
from app.persistence.artifacts import ArtifactStore
from app.persistence.metadata import MetadataStore
from app.simulation.mujoco_runner import SimulationNotAvailable
from app.simulation.runner import ENGINE_AUTO, run_candidate_simulation

logger = logging.getLogger(__name__)

_KEEPALIVE_SECONDS = 15.0
_TERMINAL_EVENT_NAMES = frozenset(name.value for name in TERMINAL_EVENTS)

CLAIM_LIMITATIONS = [
    "Links are modeled as zero-thickness line segments; the ground link is a fixed frame.",
    "Collision checks cover moving links only; contact with the frame is not modeled.",
    "Passing checks certify the implemented kinematic and geometric criteria only - not "
    "structural strength, fatigue safety, manufacturability or real-world safety.",
]


class _RunCancelled(Exception):
    """Raised internally when a run cancellation request is observed."""


class UnsupportedRequirementError(Exception):
    """Raised when a clarification answer demands checks the evaluator cannot perform."""


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
    def __init__(
        self,
        artifacts: ArtifactStore,
        metadata: MetadataStore | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._metadata = metadata
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
        if self._metadata is not None:
            self._metadata.record_candidate(run_id, record)
        return record

    def _persist(self, run_id: str) -> None:
        run = self._runs[run_id]
        self._artifacts.write_json(run_id, "run.json", run)
        if self._metadata is not None:
            self._metadata.record_run(run)

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
        registry: CapabilityRegistry | None = None,
        limits: dict[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.events = events
        self.artifacts = artifacts
        self.meta_client = meta_client or UnconfiguredMetaModelClient()
        self.max_candidates = max_candidates
        self.max_run_seconds = max_run_seconds
        self.simulation_engine = simulation_engine
        self.capabilities = registry or default_registry()
        self.limits = limits or {}
        self._cancelled: set[str] = set()

    def request_cancel(self, run_id: str) -> None:
        """Request cooperative cancellation; the pipeline stops at its next checkpoint."""
        self._cancelled.add(run_id)

    def cancel_run(self, run: DesignRun) -> DesignRun:
        """Cancel a run; paused runs are finalized immediately."""
        if run.status is RunStatus.AWAITING_CLARIFICATION:
            self._finish_cancelled(run)
            return self.store.get(run.run_id) or run
        if run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
            self.request_cancel(run.run_id)
        return self.store.get(run.run_id) or run

    def submit_clarifications(self, run_id: str, answers: dict[str, str]) -> DesignRun:
        """Apply clarification answers to the brief so the run can resume."""
        run = self.store.get(run_id)
        if run is None:
            raise ValueError(f"Unknown run {run_id!r}")
        if run.status is not RunStatus.AWAITING_CLARIFICATION:
            raise ValueError("The design run is not awaiting clarification")
        expected = {question.question_id for question in run.pending_clarifications}
        unknown = set(answers) - expected
        if unknown:
            raise ValueError(f"Unknown clarification ids: {sorted(unknown)}")
        missing = expected - set(answers)
        if missing:
            raise ValueError(f"Missing answers for: {sorted(missing)}")

        stored = self.artifacts.read_json(run_id, "brief.json")
        brief = NormalizedBrief.model_validate(stored["brief"])
        try:
            for question in run.pending_clarifications:
                brief = self._apply_answer(brief, question, answers[question.question_id])
        except UnsupportedRequirementError as exc:
            self._fail(run, "UNSUPPORTED_REQUIREMENT", str(exc))
            return self.store.get(run_id) or run

        brief = brief.model_copy(
            update={
                "clarification_questions": [
                    question
                    for question in brief.clarification_questions
                    if not question.blocking
                ]
            }
        )
        self.artifacts.write_json(
            run_id,
            "brief.json",
            {"source": stored["source"], "brief": brief.model_dump(mode="json")},
        )
        run.clarification_answers.update(answers)
        run.pending_clarifications = []
        self._update_run(run)
        return run

    @staticmethod
    def _apply_answer(
        brief: NormalizedBrief,
        question: ClarificationQuestion,
        raw_answer: str,
    ) -> NormalizedBrief:
        answer = raw_answer.strip()
        if not answer:
            raise ValueError("Clarification answers must not be empty")
        field = question.field
        sources = dict(brief.requirement_sources)
        sources[field] = RequirementSource.USER_PROVIDED
        unknowns = [unknown for unknown in brief.unknowns if unknown != field]

        if field in ("verification_scope.kinematic_only", "target_motion.type"):
            normalized = answer.lower()
            if normalized not in ("yes", "no"):
                raise ValueError("Answer must be 'yes' or 'no'")
            if normalized == "no":
                raise UnsupportedRequirementError(
                    f"The answer to '{question.question_id}' needs checks or motion the "
                    "evaluator does not implement; the run stops honestly."
                )
            assumptions = list(brief.assumptions)
            note = (
                "User confirmed: kinematic and geometric checks only; loading and "
                "environmental requirements are not evaluated."
                if field == "verification_scope.kinematic_only"
                else "User confirmed near-horizontal travel as the output motion target."
            )
            if note not in assumptions:
                assumptions.append(note)
            return brief.model_copy(
                update={
                    "assumptions": assumptions,
                    "requirement_sources": sources,
                    "unknowns": unknowns,
                }
            )

        if field in (
            "target_motion.travel_distance",
            "target_motion.trajectory_tolerance",
            "constraints.max_footprint",
        ):
            try:
                value = float(answer)
            except ValueError as exc:
                raise ValueError("Answer must be a number in millimetres") from exc
            limit = 100.0 if field.endswith("trajectory_tolerance") else 10_000.0
            if not 0.0 < value <= limit:
                raise ValueError("Answer must be a positive value within the allowed range")
            if field == "constraints.max_footprint":
                update = {
                    "constraints": brief.constraints.model_copy(
                        update={"max_footprint": value}
                    )
                }
            else:
                key = field.rsplit(".", 1)[1]
                update = {
                    "target_motion": brief.target_motion.model_copy(update={key: value})
                }
            return brief.model_copy(
                update={
                    **update,
                    "requirement_sources": sources,
                    "unknowns": unknowns,
                }
            )

        assumptions = list(brief.assumptions)
        assumptions.append(f"Clarification {question.question_id} answered: {answer}")
        return brief.model_copy(
            update={"assumptions": assumptions, "requirement_sources": sources}
        )

    def _check_cancel(self, run: DesignRun) -> None:
        if run.run_id in self._cancelled:
            raise _RunCancelled()

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
        resuming = run.status is RunStatus.AWAITING_CLARIFICATION
        self._update_run(
            run,
            status=RunStatus.RUNNING,
            stage=Stage.GENERATE_CANDIDATE if resuming else Stage.PARSE_REQUIREMENTS,
        )
        if not resuming:
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
                await self._run_pipeline(run, resuming=resuming)
        except TimeoutError:
            self._fail(
                run,
                "RUN_TIMEOUT",
                f"The design run exceeded its {self.max_run_seconds:.0f} second budget.",
            )
        except _RunCancelled:
            self._finish_cancelled(run)
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
        except UnsupportedRequirementError as exc:
            self._fail(run, "UNSUPPORTED_REQUIREMENT", str(exc))
        except Exception:
            logger.exception("Design run %s failed unexpectedly", run_id)
            self._fail(run, "INTERNAL_ERROR", "The design run failed unexpectedly.")

    async def _run_pipeline(self, run: DesignRun, *, resuming: bool = False) -> None:
        provider_calls: list[dict[str, Any]] = []
        engine_info: dict[str, Any] = {
            "name": "not_run",
            "version": None,
            "time_basis": "normalized_cycle",
            "output_point": "rocker_pin",
        }

        if resuming:
            stored = self.artifacts.read_json(run.run_id, "brief.json")
            source = stored["source"]
            brief = NormalizedBrief.model_validate(stored["brief"])
        else:
            source = (
                "meta_model" if self.meta_client.is_configured else "deterministic_fallback"
            )
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
            RunEventName.REQUIREMENTS_READY.value,
            {
                "source": source,
                "mechanism_type": brief.mechanism_type.value,
                "target_motion": brief.target_motion.model_dump(mode="json"),
                "constraints": brief.constraints.model_dump(mode="json"),
                "assumptions": brief.assumptions,
                "unknowns": brief.unknowns,
                "requirement_sources": {
                    field: source.value for field, source in brief.requirement_sources.items()
                },
                "clarifications": run.clarification_answers,
            },
        )
        blocking = [
            question for question in brief.clarification_questions if question.blocking
        ]
        if blocking:
            run.pending_clarifications = blocking
            self._update_run(run, status=RunStatus.AWAITING_CLARIFICATION)
            self.events.publish(
                run.run_id,
                RunEventName.CLARIFICATION_REQUIRED.value,
                {
                    "questions": [
                        question.model_dump(mode="json") for question in blocking
                    ],
                },
            )
            return
        assessment = route_request(
            run.original_prompt,
            brief,
            clarification_answers=run.clarification_answers,
            registry=self.capabilities,
        )
        brief = brief.model_copy(update={"capability_assessment": assessment})
        self.artifacts.write_json(
            run.run_id,
            "brief.json",
            {"source": source, "brief": brief.model_dump(mode="json")},
        )
        self.events.publish(
            run.run_id,
            RunEventName.CAPABILITY_SELECTED.value,
            {
                "capability_id": assessment.capability_id,
                "capability_version": assessment.capability_version,
                "status": assessment.status.value,
                "unsupported_requirements": assessment.unsupported_requirements,
                "unavailable_checks": assessment.unavailable_checks,
            },
        )
        if assessment.status is CapabilitySupport.NOT_SUPPORTED:
            self._complete_without_candidates(
                run, brief, source, assessment, engine_info
            )
            return
        self._check_cancel(run)

        records: list[CandidateRecord] = []
        previous: CandidateRecord | None = None
        passed_record: CandidateRecord | None = None

        for attempt in range(1, run.max_candidates + 1):
            self._check_cancel(run)
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
        no_pass = (
            final_record.evaluation is None
            or final_record.evaluation.status is not EvaluationStatus.PASSED
            or bool(assessment.unavailable_checks)
        )

        self._update_run(run, stage=Stage.REPORT)
        self._update_run(
            run,
            status=RunStatus.COMPLETED,
            stage=Stage.COMPLETED,
            final_candidate_id=final_record.candidate.candidate_id,
            no_pass=no_pass,
        )
        bundle = EvidenceBundle(
            run=run,
            prompt=run.original_prompt,
            requirements={
                "source": source,
                "brief": brief.model_dump(mode="json"),
                "capability_assessment": assessment.model_dump(mode="json"),
            },
            simulation_engine=SimulationEngineInfo(**engine_info),
            limits={
                "max_candidates": run.max_candidates,
                "max_run_seconds": self.max_run_seconds,
                "simulation_sample_count": DEFAULT_SAMPLE_COUNT,
                **self.limits,
            },
            collision_model="moving_links_only_zero_thickness",
            evaluator_version=EVALUATOR_VERSION,
            provider_calls=provider_calls,
            candidates=records,
            final_candidate_id=final_record.candidate.candidate_id,
            no_pass=no_pass,
            outcome="no_pass" if no_pass else "passed",
            limitations=CLAIM_LIMITATIONS,
            manifest=self.artifacts.manifest(run.run_id),
        )
        self.artifacts.write_json(run.run_id, "evidence.json", bundle)
        self.events.publish(
            run.run_id,
            RunEventName.ARTIFACT_READY.value,
            {
                "artifacts": [entry.name for entry in bundle.manifest]
                + ["evidence.json"],
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
                "capability_status": assessment.status.value,
                "unavailable_checks": assessment.unavailable_checks,
                "no_pass": no_pass,
            },
        )

    def _complete_without_candidates(
        self,
        run: DesignRun,
        brief: NormalizedBrief,
        source: str,
        assessment: CapabilityAssessment,
        engine_info: dict[str, Any],
    ) -> None:
        """Finish a run honestly when no registered capability can handle it."""
        self._update_run(run, stage=Stage.REPORT)
        self._update_run(
            run,
            status=RunStatus.COMPLETED,
            stage=Stage.COMPLETED,
            final_candidate_id=None,
            no_pass=True,
        )
        bundle = EvidenceBundle(
            run=run,
            prompt=run.original_prompt,
            requirements={
                "source": source,
                "brief": brief.model_dump(mode="json"),
                "capability_assessment": assessment.model_dump(mode="json"),
            },
            simulation_engine=SimulationEngineInfo(**engine_info),
            limits={
                "max_candidates": run.max_candidates,
                "max_run_seconds": self.max_run_seconds,
                "simulation_sample_count": DEFAULT_SAMPLE_COUNT,
                **self.limits,
            },
            collision_model="moving_links_only_zero_thickness",
            evaluator_version=EVALUATOR_VERSION,
            candidates=[],
            final_candidate_id=None,
            no_pass=True,
            outcome="not_supported",
            limitations=CLAIM_LIMITATIONS,
            manifest=self.artifacts.manifest(run.run_id),
        )
        self.artifacts.write_json(run.run_id, "evidence.json", bundle)
        self.events.publish(
            run.run_id,
            RunEventName.ARTIFACT_READY.value,
            {
                "artifacts": [entry.name for entry in bundle.manifest]
                + ["evidence.json"],
            },
        )
        self.events.publish(
            run.run_id,
            RunEventName.RUN_COMPLETED.value,
            {
                "status": "not_supported",
                "stage": run.stage.value,
                "final_candidate_id": None,
                "failed_constraints": [],
                "capability_status": assessment.status.value,
                "unavailable_checks": assessment.unavailable_checks,
                "unsupported_requirements": assessment.unsupported_requirements,
                "no_pass": True,
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

    def _finish_cancelled(self, run: DesignRun) -> None:
        self._update_run(run, status=RunStatus.CANCELLED, stage=Stage.CANCELLED)
        self.events.publish(
            run.run_id,
            RunEventName.RUN_CANCELLED.value,
            {
                "status": run.status.value,
                "stage": run.stage.value,
            },
        )


def render_evidence_report(
    run: DesignRun,
    candidates: list[CandidateRecord],
    bundle: EvidenceBundle | None,
) -> str:
    """Render a human-readable evidence report for a run."""
    lines = [
        "Mechanism AI evidence report",
        f"Run: {run.run_id}",
        f"Prompt: {run.original_prompt}",
        f"Status: {run.status.value}"
        + (f" ({run.error_code})" if run.error_code else ""),
        "Outcome: "
        + (
            "no valid candidate found"
            if run.no_pass
            else ("passed" if run.status is RunStatus.COMPLETED else run.status.value)
        ),
    ]
    if bundle is not None:
        engine = bundle.simulation_engine
        lines.append(
            f"Engine: {engine.name}"
            + (f" {engine.version}" if engine.version else "")
            + f" · evaluator {bundle.evaluator_version}"
        )
        lines.append(f"Requirements source: {bundle.requirements.get('source')}")
        assessment_data = bundle.requirements.get("capability_assessment")
        if assessment_data:
            lines.append(
                f"Capability: {assessment_data.get('capability_id')} "
                f"{assessment_data.get('capability_version')} - {assessment_data.get('status')}"
            )
            for item in assessment_data.get("unsupported_requirements", []):
                lines.append(f"- Not evaluated: {item}")
            for item in assessment_data.get("unavailable_checks", []):
                lines.append(f"- Unresolved required check: {item}")
    final = next(
        (
            record
            for record in candidates
            if record.candidate.candidate_id == run.final_candidate_id
        ),
        candidates[-1] if candidates else None,
    )
    if final is not None and final.evaluation is not None:
        evaluation = final.evaluation
        lines.append(
            f"Final candidate: {final.candidate.candidate_id} "
            f"(attempt {final.candidate.attempt_number}) - {evaluation.status.value}"
        )
        metrics = evaluation.metrics
        lines.append(
            f"Measured: travel {metrics.travel_distance_mm:.2f} mm · "
            f"footprint {metrics.footprint_mm:.2f} mm · "
            f"trajectory error {metrics.trajectory_error_mm:.2f} mm"
        )
        if evaluation.failed_constraints:
            lines.append(
                "Unresolved checks: " + ", ".join(evaluation.failed_constraints)
            )
        for note in evaluation.diagnostic_notes:
            lines.append(f"- {note}")
    if bundle is not None:
        if bundle.manifest:
            lines.append("Artifacts:")
            lines.extend(
                f"- {entry.name} (sha256 {entry.sha256[:12]}…)" for entry in bundle.manifest
            )
        if bundle.limitations:
            lines.append("Limitations:")
            lines.extend(f"- {item}" for item in bundle.limitations)
    return "\n".join(lines)
