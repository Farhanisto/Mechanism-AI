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
- MuJoCo closed-loop simulation (optional `sim` extra): deterministic versioned MJCF compiler,
  kinematic crank drive with bounded settle steps, structured failures, and a reference-trajectory
  comparison recorded per candidate
- Meta Model API adapter (`muse-spark-1.3`) with strict JSON schemas, bounded retries and typed
  errors; mocked HTTP tests never call the live API
- Deterministic offline fallback for briefs and candidates when no key is configured
- Clarification workflow: requirement provenance and explicit unknowns, blocking questions
  pause the run until answered, answers update the brief and the evidence bundle
- Capability registry and routing: registered capabilities with test status, honest
  supported/partial/not-supported assessments, and unresolved required checks that block a pass
- Bounded candidate loop with evaluator feedback fed into the next attempt
- Independent evaluator and path metrics, tested without any LLM call
- Reviewed benchmark suites with recorded results: evaluator classification
  (pass/fail/boundary/invalid cases) and bounded repair (see `apps/api/benchmarks/`)
- JSON evidence persistence per run: run, brief, candidates, simulations and evidence bundle,
  with SHA-256 artifact hashes, timestamps and SQLite metadata for reconstruction
- React + TypeScript + Vite UI with prompt form, live event log, validation report, candidate
  history and a rendered reference trace
- Docker Compose setup for the API and web app

Not wired yet:

1. Physical link thickness, obstacle geometry and a broader collision model. The MVP checks
   zero-thickness moving links and treats the ground link as a fixed frame.
2. A broader independently reviewed benchmark suite and a formal physical-feasibility review.

A candidate that fails evaluation produces a completed run with `no_pass: true`, not a fake
success. Infrastructure and model failures use `run_failed` with a safe error code.

## Quick start

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+.

API:

```bash
cd apps/api
uv sync            # add --extra sim to enable the MuJoCo engine
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

The API image includes the `sim` extra, so container runs use the MuJoCo engine unless
`MECHANISM_AI_SIMULATION_ENGINE=reference` is set.

`.env` is optional. Without `MECHANISM_AI_META_API_KEY`, runs use the deterministic offline
fallback. With a key, the Meta adapter parses the brief and proposes candidates. The base URL and
model default to `https://api.meta.ai/v1` and `muse-spark-1.3`.

## Configuration

All server settings use the `MECHANISM_AI_` prefix (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `MECHANISM_AI_ARTIFACTS_DIR` | `data/artifacts` | Root directory for JSON evidence bundles (relative to the API process) |
| `MECHANISM_AI_MAX_CANDIDATES` | `3` | Server cap; per-run option is 1-3 |
| `MECHANISM_AI_SIMULATION_ENGINE` | `auto` | `auto`, `reference` or `mujoco`; `auto` uses MuJoCo when the `sim` extra is installed |
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

## Simulation engines

Every simulation artifact and event is labelled with the engine that produced it
(`reference_kinematics` or `mujoco`), its version and its settings.

- **Reference engine**: closed-form four-bar kinematics on one assembly branch. Used on its own
  when the `sim` extra is not installed (including the Docker images), and as the comparison
  baseline for MuJoCo.
- **MuJoCo engine** (`uv sync --extra sim`): the candidate is compiled by a deterministic,
  versioned `Candidate -> MJCF` compiler (no model-generated MJCF). The loop is closed with a
  `connect` equality between the coupler end and the rocker tip in a reference configuration
  assembled at the requested start angle. The input crank is driven kinematically: at each sample
  it is pinned at the commanded angle and the loop is settled with at most 200 steps to a
  0.0001 mm closure target. Solver settings: Newton, `implicitfast`, timestep 1 ms, equality
  `solref (0.0021, 0.95)`, `solimp (1, 1, 0.001)`, contacts disabled (collision acceptance stays
  with the evaluator's deterministic geometry checks).

Comparison method: when MuJoCo produces a valid trace, the same candidate is replayed with the
reference solver at identical normalized sampling, and the index-aligned Euclidean deviation
between output points is recorded in `diagnostics.reference_comparison`. The documented tolerance
is **0.05 mm**; observed deviation on the fallback linkages is below 0.001 mm. A candidate that
cannot close the loop, turns non-finite, or is not assemblable at the start angle produces a
structured `simulation_valid: false` result with a failure reason, never a crash.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/design-runs` | Validate a prompt and start a run |
| `GET` | `/api/v1/design-runs/{run_id}` | Run status, stage, error code, final candidate |
| `GET` | `/api/v1/design-runs/{run_id}/events` | SSE progress stream (replays history first) |
| `GET` | `/api/v1/design-runs/{run_id}/candidates` | Candidate parameters and evaluations |
| `GET` | `/api/v1/design-runs/{run_id}/evidence` | Evidence summary, human-readable report, artifact manifest with hashes |
| `POST` | `/api/v1/design-runs/{run_id}/clarifications` | Answer blocking clarification questions and resume the run |
| `POST` | `/api/v1/design-runs/{run_id}/cancel` | Request cooperative cancellation (idempotent) |
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
adapter tests use `httpx.MockTransport`; a live smoke test is intentionally opt-in. Compiler,
MuJoCo runner and reference-comparison tests run when the `sim` extra is installed and skip
otherwise. The reviewed benchmark suites in `apps/api/benchmarks/` run as part of the suite;
their recorded results and assumptions live in `apps/api/benchmarks/README.md`.

## Repository layout

```
apps/
  api/
    app/
      api/            # HTTP routes (design runs, artifacts, health)
      ai/             # Meta model protocol, requirement and candidate parsers
      mechanism/      # Pydantic schemas, reference kinematics, MJCF compiler
      simulation/     # Engine selection, reference runner, MuJoCo runner, comparisons
      evaluation/     # Evaluator, metrics, geometry/collision checks
      orchestration/  # Run lifecycle, SSE broker, repair loop
      persistence/    # Atomic JSON artifact store and SQLite metadata
    tests/            # Schema, evaluator, metrics and API tests
  web/
    src/
      features/       # design-input, simulation, validation-report, candidate-history
      components/     # Shared UI pieces
      lib/            # Typed API client and run hook
docker-compose.yml
```

## Demo script

Scenario A, the verified four-bar path (measured end to end in the recorded rehearsal,
`apps/api/benchmarks/README.md`, 6-11 seconds per run):

1. Enter a linkage request, e.g. "Design a compact four-bar linkage with ~100 mm
   near-horizontal travel in a 200 mm footprint" (candidate budget 1-3).
2. Show the parsed requirements and their labelled assumptions in the report panel.
3. Watch the run stages stream in the event log (parse -> generate -> simulate ->
   evaluate -> repair -> report).
4. Show the candidate history: a failing candidate with its measured misses and, when
   the budget allows, the repaired candidate that passes.
5. Open the validation report: measured metrics, failed constraints and the evaluator
   version.
6. Inspect the persisted evidence (`run`, `brief`, `candidates`, `simulation_*`,
   `evidence` JSON artifacts) and note the engine, its version and settings.
7. Repeat with an impossible prompt ("500 mm of travel inside a 100 mm footprint"):
   the run completes as `no pass` with the conflicting constraints named - never a
   fake success.

Scenario B (broad mechanical prompts with clarification and capability routing) is
part of the extension work tracked in issues #8-#14 and is not demoable yet.

## Honest claims

A result from this system can only claim that a candidate passed the implemented kinematic and
geometric checks under the saved configuration. Simulation runs on the deterministic reference
solver or on MuJoCo's closed-loop solver (each result is labelled with its engine and settings),
but links are zero-thickness line segments, the ground link is a fixed frame, contact with the
frame is not modeled, and the output point is the rocker pin. It cannot claim structural strength,
fatigue safety, manufacturability, real-world collision safety, or physical fidelity. The UI and
report surface assumptions, failed constraints, evaluator version and simulation settings; a
no-pass run stays a no-pass run.
