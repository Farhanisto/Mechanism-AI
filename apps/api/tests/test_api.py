from collections.abc import Iterator

import pytest
from app.config import get_settings
from app.main import app
from app.simulation.mujoco_runner import is_mujoco_available
from fastapi.testclient import TestClient

ENGINE_LABELS = {"reference": "reference_kinematics", "mujoco": "mujoco"}

PROMPT = (
    "Design a compact four-bar linkage that produces approximately 100 mm of "
    "near-horizontal movement and fits within a 200 mm footprint."
)


@pytest.fixture(params=["reference", "mujoco"])
def engine_name(request: pytest.FixtureRequest) -> str:
    if request.param == "mujoco" and not is_mujoco_available():
        pytest.skip("mujoco is not installed")
    return request.param


@pytest.fixture
def client(engine_name: str, tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MECHANISM_AI_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("MECHANISM_AI_META_API_KEY", "")
    monkeypatch.setenv("MECHANISM_AI_META_MODEL", "")
    monkeypatch.setenv("MECHANISM_AI_META_API_BASE_URL", "")
    monkeypatch.setenv("MECHANISM_AI_SIMULATION_ENGINE", engine_name)
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_run_completes_with_a_passing_candidate(client: TestClient) -> None:
    response = client.post("/api/v1/design-runs", json={"prompt": PROMPT})
    assert response.status_code == 202

    run_id = response.json()["run_id"]
    run = client.get(f"/api/v1/design-runs/{run_id}").json()

    assert run["status"] == "completed"
    assert run["stage"] == "completed"
    assert run["error_code"] is None
    assert run["final_candidate_id"] == "candidate_001"
    assert run["no_pass"] is False
    assert run["max_candidates"] == 3


def test_events_replay_for_finished_run(client: TestClient) -> None:
    run_id = client.post("/api/v1/design-runs", json={"prompt": PROMPT}).json()["run_id"]

    response = client.get(f"/api/v1/design-runs/{run_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: run_started" in response.text
    assert "event: requirements_ready" in response.text
    assert "event: candidate_generated" in response.text
    assert "event: simulation_completed" in response.text
    assert "event: evaluation_completed" in response.text
    assert "event: run_completed" in response.text
    assert "event: run_failed" not in response.text


def test_fallback_candidate_passes_the_demo_targets(client: TestClient) -> None:
    run_id = client.post("/api/v1/design-runs", json={"prompt": PROMPT}).json()["run_id"]

    response = client.get(f"/api/v1/design-runs/{run_id}/candidates")

    assert response.status_code == 200
    candidates = response.json()
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["candidate"]["candidate_id"] == "candidate_001"
    assert candidate["evaluation"]["status"] == "passed"
    assert candidate["evaluation"]["failed_constraints"] == []
    metrics = candidate["evaluation"]["metrics"]
    assert metrics["travel_distance_mm"] == pytest.approx(99.51, abs=0.01)
    assert metrics["footprint_mm"] == pytest.approx(181.97, abs=0.01)
    assert metrics["trajectory_error_mm"] == pytest.approx(4.14, abs=0.01)
    assert metrics["cycle_completed"] is True
    assert metrics["collision_free"] is True
    assert metrics["simulation_valid"] is True


def test_run_artifacts_are_persisted(client: TestClient, engine_name: str) -> None:
    run_id = client.post("/api/v1/design-runs", json={"prompt": PROMPT}).json()["run_id"]

    run_response = client.get(f"/api/v1/design-runs/{run_id}/artifacts/run.json")
    brief_response = client.get(f"/api/v1/design-runs/{run_id}/artifacts/brief.json")
    simulation_response = client.get(
        f"/api/v1/design-runs/{run_id}/artifacts/simulation_candidate_001.json"
    )
    evidence_response = client.get(f"/api/v1/design-runs/{run_id}/artifacts/evidence.json")

    assert run_response.status_code == 200
    assert run_response.json()["run_id"] == run_id
    assert brief_response.status_code == 200
    assert brief_response.json()["source"] == "deterministic_fallback"
    assert simulation_response.status_code == 200
    assert simulation_response.json()["engine"] == ENGINE_LABELS[engine_name]
    assert len(simulation_response.json()["samples"]) == 361
    assert evidence_response.status_code == 200
    assert evidence_response.json()["no_pass"] is False
    assert evidence_response.json()["final_candidate_id"] == "candidate_001"


def test_no_pass_run_completes_without_claiming_success(client: TestClient) -> None:
    prompt = "Design a four-bar linkage with 500 mm of travel inside a 100 mm footprint."

    run_id = client.post(
        "/api/v1/design-runs",
        json={"prompt": prompt, "options": {"max_candidates": 1}},
    ).json()["run_id"]
    run = client.get(f"/api/v1/design-runs/{run_id}").json()
    candidates = client.get(f"/api/v1/design-runs/{run_id}/candidates").json()

    assert run["status"] == "completed"
    assert run["no_pass"] is True
    assert run["error_code"] is None
    assert candidates[0]["evaluation"]["status"] == "failed"
    assert "travel_distance" in candidates[0]["evaluation"]["failed_constraints"]


def test_missing_run_and_artifact_return_404(client: TestClient) -> None:
    assert client.get("/api/v1/design-runs/run_missing").status_code == 404
    assert (
        client.get("/api/v1/design-runs/run_missing/artifacts/run.json").status_code == 404
    )


def test_artifact_name_traversal_is_rejected(client: TestClient) -> None:
    run_id = client.post("/api/v1/design-runs", json={"prompt": PROMPT}).json()["run_id"]

    response = client.get(f"/api/v1/design-runs/{run_id}/artifacts/..%2Frun.json")

    assert response.status_code in {400, 404}


def test_invalid_prompt_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/design-runs", json={"prompt": ""})

    assert response.status_code == 422


def test_cancel_endpoint_is_idempotent(client: TestClient) -> None:
    run_id = client.post("/api/v1/design-runs", json={"prompt": PROMPT}).json()["run_id"]

    response = client.post(f"/api/v1/design-runs/{run_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] in ("completed", "cancelled")

    missing = client.post("/api/v1/design-runs/run_missing/cancel")
    assert missing.status_code == 404


def test_evidence_endpoint_returns_summary_report_and_manifest(client: TestClient) -> None:
    run_id = client.post("/api/v1/design-runs", json={"prompt": PROMPT}).json()["run_id"]

    response = client.get(f"/api/v1/design-runs/{run_id}/evidence")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["run_id"] == run_id
    assert payload["summary"]["outcome"] == "passed"
    assert payload["summary"]["evaluator_version"]
    assert payload["report"].startswith("Mechanism AI evidence report")
    assert "Limitations:" in payload["report"]
    assert payload["evidence_bundle"]["outcome"] == "passed"
    names = {entry["name"] for entry in payload["manifest"]}
    assert {"run.json", "brief.json", "candidates.json", "evidence.json"} <= names
    for entry in payload["manifest"]:
        assert len(entry["sha256"]) == 64

    missing = client.get("/api/v1/design-runs/run_missing/evidence")
    assert missing.status_code == 404
