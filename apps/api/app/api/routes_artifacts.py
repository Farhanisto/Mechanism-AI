from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response

from app.orchestration.design_run import DesignRunOrchestrator

router = APIRouter(prefix="/design-runs", tags=["artifacts"])

_MEDIA_TYPES = {
    ".stl": "model/stl",
    ".step": "application/step",
    ".stp": "application/step",
}


def _orchestrator(request: Request) -> DesignRunOrchestrator:
    return request.app.state.orchestrator


@router.get("/{run_id}/artifacts/{name}")
def get_artifact(run_id: str, name: str, request: Request) -> Any:
    orchestrator = _orchestrator(request)
    if orchestrator.store.get(run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design run not found")
    lowered = name.lower()
    try:
        if lowered.endswith(".json"):
            payload = orchestrator.artifacts.read_json(run_id, name)
        else:
            payload = orchestrator.artifacts.read_bytes(run_id, name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    if isinstance(payload, bytes):
        suffix = "." + lowered.rsplit(".", 1)[-1]
        return Response(
            content=payload,
            media_type=_MEDIA_TYPES.get(suffix, "application/octet-stream"),
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )
    return payload
