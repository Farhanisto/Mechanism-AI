from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.orchestration.design_run import DesignRunOrchestrator

router = APIRouter(prefix="/design-runs", tags=["artifacts"])


def _orchestrator(request: Request) -> DesignRunOrchestrator:
    return request.app.state.orchestrator


@router.get("/{run_id}/artifacts/{name}")
def get_artifact(run_id: str, name: str, request: Request) -> Any:
    orchestrator = _orchestrator(request)
    if orchestrator.store.get(run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design run not found")
    try:
        payload = orchestrator.artifacts.read_json(run_id, name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return payload
