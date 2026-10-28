# Mechanism AI

A constraint-driven mechanical design agent for planar four-bar linkages, scaffolded from
`Mechanism_AI_End_to_End_Architecture_and_Workflow.pdf`.

The core principle is fixed: **the AI proposes; an independent evaluator decides whether a
candidate passes.** The evaluator runs deterministic checks, owns pass/fail, and never changes
its acceptance criteria based on model output.

## Project status

Working today:

- FastAPI run lifecycle: create a run, poll it, stream progress over SSE, list candidates, read
  JSON artifacts
- Pydantic schemas for briefs, candidates, metrics, evaluations and runs; model output is parsed
  into typed data only
- Deterministic four-bar reference kinematics with full-cycle, collision, travel, footprint and
  near-horizontal path checks
- Meta Model API adapter (`muse-spark-1.3`) with strict JSON schemas, bounded retries and typed
  errors; mocked HTTP tests never call the live API
- Deterministic offline fallback for briefs and candidates when no key is configured
- Bounded candidate loop with evaluator feedback fed into the next attempt
- Independent evaluator and path metrics, tested without any LLM call
- JSON evidence persistence per run: run, brief, candidates, simulations and evidence bundle
- React + TypeScript + Vite UI with prompt form, live event log, validation report, candidate
  history and a rendered reference trace
- Docker Compose setup for the API and web app

Not wired yet:

1. MuJoCo closed-loop simulation and trajectory comparison (Milestone 2). Runs are labelled
   `reference_kinematics`, not MuJoCo.
2. Physical link thickness, obstacle geometry and a broader collision model. The MVP checks
   zero-thickness moving links and treats the ground link as a fixed frame.
3. The full PRD benchmark suite and a formal physical-feasibility review.

A candidate that fails evaluation produces a completed run with `no_pass: true`, not a fake
success. Infrastructure and model failures use `run_failed` with a safe error code.

## Quick start

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+.

API:

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Web (in a second terminal):

```bash
cd apps/web
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to the local API. Interactive API docs are at
<http://localhost:8000/docs>.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

- Web: <http://localhost:5173>
- API: <http://localhost:8000>
- Artifacts persist in the `mechanism-data` volume

`.env` is optional. Without `MECHANISM_AI_META_API_KEY`, runs use the deterministic offline
fallback. With a key, the Meta adapter parses the brief and proposes candidates. The base URL and
model default to `https://api.meta.ai/v1` and `muse-spark-1.3`.

## Configuration

All server settings use the `MECHANISM_AI_` prefix (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `MECHANISM_AI_ARTIFACTS_DIR` | `data/artifacts` | Root directory for JSON evidence bundles (relative to the API process) |
| `MECHANISM_AI_MAX_CANDIDATES` | `3` | Server cap; per-run option is 1-3 |
| `MECHANISM_AI_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed browser origins (JSON list) |
| `MECHANISM_AI_META_API_BASE_URL` | `https://api.meta.ai/v1` | OpenAI-compatible provider base URL |
| `MECHANISM_AI_META_API_KEY` | unset | Server-side provider key; unset enables the offline fallback |
| `MECHANISM_AI_META_MODEL` | `muse-spark-1.3` | Model identifier |
| `MECHANISM_AI_META_REASONING_EFFORT` | `minimal` | `minimal`, `low`, `medium`, `high`, `xhigh` or `max` |
| `MECHANISM_AI_META_TIMEOUT_SECONDS` | `45` | Per-request timeout |
| `MECHANISM_AI_META_MAX_RETRIES` | `1` | Retries for timeouts, network errors and retryable HTTP statuses |
| `MECHANISM_AI_META_MAX_OUTPUT_TOKENS` | `8192` | Output-token bound per model call |
| `MECHANISM_AI_API_PORT` | `8000` | Docker host port for the API |
| `MECHANISM_AI_WEB_PORT` | `5173` | Docker host port for the web app |

API keys stay on the server. Model output is treated as untrusted data and validated with
Pydantic; it is never executed. The default `minimal` reasoning effort keeps the demo within the
60-second target; raise it for harder briefs at the cost of latency.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/design-runs` | Validate a prompt and start a run |
| `GET` | `/api/v1/design-runs/{run_id}` | Run status, stage, error code, final candidate |
| `GET` | `/api/v1/design-runs/{run_id}/events` | SSE progress stream (replays history first) |
| `GET` | `/api/v1/design-runs/{run_id}/candidates` | Candidate parameters and evaluations |
| `GET` | `/api/v1/design-runs/{run_id}/artifacts/{name}` | Persisted JSON artifact, e.g. `run.json` |
| `GET` | `/api/v1/health` | Health check |

Artifacts per run: `run.json`, `brief.json`, `candidates.json`, `simulation_<candidate_id>.json`
(full sampled trace), `evidence.json`, and `error.json` for failed infrastructure/model runs.

Example:

```bash
curl -s -X POST http://localhost:8000/api/v1/design-runs \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Design a compact four-bar linkage with ~100 mm near-horizontal travel in a 200 mm footprint"}'
```

## Tests and checks

```bash
cd apps/api
uv run pytest
uv run ruff check .

cd ../web
npm run typecheck
npm run build
```

Evaluator, kinematics, parser and API tests run without a live model or simulator. The Meta
adapter tests use `httpx.MockTransport`; a live smoke test is intentionally opt-in.

## Repository layout

```
apps/
  api/
    app/
      api/            # HTTP routes (design runs, artifacts, health)
      ai/             # Meta model protocol, requirement and candidate parsers
      mechanism/      # Pydantic schemas, reference kinematics, MJCF compiler
      simulation/     # Reference runner now; MuJoCo runner arrives in Milestone 2
      evaluation/     # Evaluator, metrics, geometry/collision checks
      orchestration/  # Run lifecycle, SSE broker, repair loop
      persistence/    # Atomic JSON artifact store
    tests/            # Schema, evaluator, metrics and API tests
  web/
    src/
      features/       # design-input, simulation, validation-report, candidate-history
      components/     # Shared UI pieces
      lib/            # Typed API client and run hook
docker-compose.yml
```

## Honest claims

A result from this system can only claim that a candidate passed the implemented kinematic and
geometric checks under the saved configuration. The current engine is a deterministic reference
solver, not MuJoCo: links are zero-thickness line segments, the ground link is a fixed frame,
contact with the frame is not modeled, and the output point is the rocker pin. It cannot claim
structural strength, fatigue safety, manufacturability, real-world collision safety, or physical
fidelity. The UI and report surface assumptions, failed constraints, evaluator version and
simulation settings; a no-pass run stays a no-pass run.
