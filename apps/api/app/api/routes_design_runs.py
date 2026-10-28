from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.mechanism.schemas import CandidateRecord, DesignRun, DesignRunCreateRequest
from app.orchestration.design_run import DesignRunOrchestrator

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
