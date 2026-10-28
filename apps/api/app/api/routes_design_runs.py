from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.mechanism.schemas import (
    CandidateRecord,
    DesignRun,
    DesignRunCreateRequest,
    EvidenceBundle,
    RunStatus,
)
from app.orchestration.design_run import (
    DesignRunOrchestrator,
    render_evidence_report,
)

router = APIRouter(prefix="/design-runs", tags=["design-runs"])


def _orchestrator(request: Request) -> DesignRunOrchestrator:
    return request.app.state.orchestrator


def _require_run(orchestrator: DesignRunOrchestrator, run_id: str) -> DesignRun:
    run = orchestrator.store.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design run not found")
    return run


@router.post("", response_model=DesignRun, status_code=status.HTTP_202_ACCEPTED)
async def create_design_run(
    payload: DesignRunCreateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> DesignRun:
    orchestrator = _orchestrator(request)
    run = orchestrator.create_run(payload)
    background_tasks.add_task(orchestrator.execute, run.run_id)
    return run


@router.get("/{run_id}", response_model=DesignRun)
def get_design_run(run_id: str, request: Request) -> DesignRun:
    return _require_run(_orchestrator(request), run_id)


@router.get("/{run_id}/events")
async def design_run_events(run_id: str, request: Request) -> StreamingResponse:
    orchestrator = _orchestrator(request)
    _require_run(orchestrator, run_id)

    async def stream() -> AsyncIterator[str]:
        async for event in orchestrator.events.stream(run_id):
            yield ": keep-alive\n\n" if event is None else event.to_sse()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{run_id}/candidates", response_model=list[CandidateRecord])
def list_candidates(run_id: str, request: Request) -> list[CandidateRecord]:
    orchestrator = _orchestrator(request)
    _require_run(orchestrator, run_id)
    return orchestrator.store.list_candidates(run_id)


@router.post("/{run_id}/cancel", response_model=DesignRun)
def cancel_design_run(run_id: str, request: Request) -> DesignRun:
    orchestrator = _orchestrator(request)
    run = _require_run(orchestrator, run_id)
    if run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
        orchestrator.request_cancel(run_id)
        run = orchestrator.store.get(run_id) or run
    return run


@router.get("/{run_id}/evidence")
def design_run_evidence(run_id: str, request: Request) -> dict:
    orchestrator = _orchestrator(request)
    run = _require_run(orchestrator, run_id)
    candidates = orchestrator.store.list_candidates(run_id)
    bundle_raw = orchestrator.artifacts.read_json(run_id, "evidence.json")
    bundle = (
        EvidenceBundle.model_validate(bundle_raw) if bundle_raw is not None else None
    )
    manifest = [
        entry.model_dump(mode="json") for entry in orchestrator.artifacts.manifest(run_id)
    ]
    return {
        "summary": {
            "run_id": run.run_id,
            "status": run.status.value,
            "stage": run.stage.value,
            "error_code": run.error_code,
            "no_pass": run.no_pass,
            "final_candidate_id": run.final_candidate_id,
            "outcome": (
                bundle.outcome
                if bundle is not None
                else ("failed" if run.status is RunStatus.FAILED else run.status.value)
            ),
            "evaluator_version": bundle.evaluator_version if bundle is not None else None,
            "candidate_count": len(candidates),
        },
        "report": render_evidence_report(run, candidates, bundle),
        "manifest": manifest,
        "evidence_bundle": bundle_raw,
    }
