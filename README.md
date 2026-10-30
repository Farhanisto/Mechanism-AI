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
- Parametric CAD: deterministic CadQuery/OpenCascade link-set compiler producing validated STL
  geometry artifacts with SHA-256 hashes (optional `cad` extra)
- Model-authored design programs: the Meta model composes `custom_part` solids, multi-part
  `assembly` designs (named parts + revolute joints) and static `structural_frame` structures
  (trusses, beams, decks) as CadQuery code; a sandbox executes them and an independent evaluator
  verifies the exported meshes, articulation and overall dimensions
- Three-panel React + TypeScript + Vite workspace with an interactive Three.js CAD viewport (from the
  persisted STL artifact), motion preview from computed traces, an explicit concept/unavailable
  mode, Beginner/Expert views, validation report, candidate history and artifact downloads
- Docker Compose setup for the API and web app

Not wired yet:

1. Collision evaluation still treats links as zero-thickness line segments; the generated CAD
   link set has bar width and thickness, but obstacles and frame contact are not modeled.
2. A broader independently reviewed benchmark suite and a formal physical-feasibility review.

A candidate that fails evaluation produces a completed run with `no_pass: true`, not a fake
success. Infrastructure and model failures use `run_failed` with a safe error code.

## Quick start

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+.

API:

```bash
cd apps/api
uv sync            # add --extra sim for MuJoCo and --extra cad for CAD geometry
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

API keys stay on the server. Structured model output is treated as untrusted data and validated
with Pydantic. For the `custom_part` capability the model writes CadQuery code, which runs only
inside the program sandbox described below - never in the API process and never as shell. The
default `minimal` reasoning effort keeps the demo within the 60-second target; raise it for
harder briefs at the cost of latency.

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

## Geometry artifacts

Supported candidates are compiled into parametric CAD geometry with CadQuery/OpenCascade
(`uv sync --extra cad`). Open decision 1 is resolved as **STL first**: binary STL is the validated
export format because it is deterministic, directly renderable, and verifiable; STEP export is
deferred until a determinism and round-trip strategy for its timestamped header is defined.

- The server builds a typed `DesignPlan` (components, joints, whitelisted geometry operations,
  required checks, resource budget) from the evaluated candidate - plans are data and never
  contain code. The compiler rejects unsupported capabilities, operations, joint/component kinds,
  out-of-range parameters and geometry that disagrees with the declared link lengths.
- Compilation uses fixed tessellation tolerances, so the same plan and compiler version produce
  byte-identical STL output. The SHA-256 hash is recorded in `geometry_artifacts` in the evidence
  bundle, the artifact manifest and the SQLite metadata.
- Validation results are stored with every artifact: non-empty mesh, all joints inside the mesh
  bounding box, positive closed volume and export size within the plan budget. Failed validation
  is reported honestly and the artifact is not advertised as generated.
- Artifacts are downloadable as binary (`GET /api/v1/design-runs/{run_id}/artifacts/geometry_*.stl`,
  `model/stl`); the `geometry_validated` event reports each candidate's artifact and hash.
- Limitations: the link set is a planar four-bar with rectangular bars and pin holes; no fillets,
  threads, fasteners, obstacles or frame contact are modeled.

## Model-authored design programs

The four-bar linkage is the hand-coded reference path. The `custom_part` capability shows the
extension architecture the product is built for: **the model composes the design logic, engineering
tools execute it, and the evaluator verifies the result.**

1. **Routing.** Prompts that match no specific capability keyword do not fail fast: when the Meta
   model is configured they fall back to this capability, so the model decides whether the request
   can be expressed as (simplified) solid geometry. Without a model the request is reported
   unsupported.
2. **Requirements.** The model turns the request into a typed `PartBrief`: one static solid, or a
   simplified representative geometry for a larger product (for example a motorcycle-helmet
   shell). It names exactly what geometry is produced and lists every omitted component,
   mechanism and analysis in `unsupported_requirements`, which makes the capability status
   **partial**. Safety-critical requests (helmets, protective gear, certification) pause for an
   explicit confirmation that only geometric checks are performed.
3. **Design program.** The model returns a `DesignProgram`: a CadQuery Python source that defines
   `build()` and returns a Workplane/Shape/Compound, plus declared parameters and the expected
   bounding box. The source is stored verbatim as an artifact (`program_XXX.py`) with its SHA-256.
4. **Sandboxed execution.** The program runs in a separate, isolated subprocess
   (`app/programs/bootstrap.py`):
   - isolated working directory, minimal environment (no API keys or secrets), `-I` isolated mode
   - import allowlist: `cadquery`, `math`, `numpy`, `typing` only
   - curated builtins (no `open`, `eval`, `exec`, `compile`, attribute dunders), plus static
     rejection of forbidden constructs before execution
   - CPU, file-size and wall-clock limits; memory limits where the platform permits
   - fixed tessellation tolerances so identical programs produce identical STL bytes

   This is a **best-effort sandbox, not a hardened OS boundary**: model code never runs in the API
   process, but production deployments should also run the API in a container without network
   access or credentials.
5. **Assemblies.** For the `assembly` capability `build()` returns named parts plus revolute joint
   declarations (`parent`, `child`, `origin`, `axis`, `min_deg`, `max_deg`). Each part is exported
   separately and as a combined mesh; the evaluator additionally requires at least two parts, at
   least one valid joint, and **articulation clearance**: the child part is rotated through the
   declared range and must not interpenetrate the parent (penetration deeper than 0.2 mm fails).
   Only the declared jointed pair is checked; pins, bores and hardware clearances are not verified.
6. **Structures.** For the `structural_frame` capability `build()` returns only named parts
   (joints are optional). Checks require at least four closed solids, the assembled span to match
   the requested envelope (at least 90% of the largest requested dimension), the envelope bounds
   (5% overall tolerance),
   determinism and export size. Connection plates, bolt holes and overlaps at joints are allowed
   as geometry; **no load, deflection, joint-strength or safety analysis is performed** and the
   evidence bundle says so explicitly.
7. **Independent evaluation.** Fixed checks in `app/evaluation/part_evaluator.py` judge the exported
   meshes, not the program: program executed, meshes valid (closed volume), measured width/height/
   thickness within the requested envelope, deterministic (two runs produce the same mesh hashes),
   export size within budget, and for assemblies the parts/joints/articulation checks above.
   Thresholds live in code; model output cannot change them.
8. **Bounded repair.** Failed checks and execution errors feed back into the next program attempt
   (up to three). Exhausted budgets end as an honest `no_pass` with the failed checks named; the
   best attempt is reported.

Artifacts per attempt: the program source, the STL mesh and `programs.json`; hashes appear in the
evidence bundle and SQLite metadata. The CAD tab renders the accepted mesh, and the UI labels
everything as verified artifact, computed trace or unavailable. Without a configured Meta model the
capability reports itself unsupported instead of pretending.

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
| `GET` | `/api/v1/design-runs/{run_id}/artifacts/{name}` | Persisted artifact: JSON (`run.json`) or binary (`geometry_*.stl`) |
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

Evaluator, kinematics, parser and API tests run without a live model or simulator. CAD tests
run when the `cad` extra is installed and skip otherwise. The web app has vitest UI tests
(`cd apps/web && npm test`). The Meta
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
      features/       # design-input, clarifications, requirements, workspace (3D), simulation,
                      # validation-report, candidate-history, evidence
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

A result from this system can only claim that a candidate passed the implemented kinematic,
geometric and mesh checks under the saved configuration. Model-authored design programs are
executed in a best-effort sandbox and only their exported mesh is verified; no check proves the
program is safe, correct beyond the measured mesh, or free of side effects. Simulation runs on the deterministic reference
solver or on MuJoCo's closed-loop solver (each result is labelled with its engine and settings),
but links are zero-thickness line segments, the ground link is a fixed frame, contact with the
frame is not modeled, and the output point is the rocker pin. It cannot claim structural strength,
fatigue safety, manufacturability, real-world collision safety, or physical fidelity. The UI and
report surface assumptions, failed constraints, evaluator version and simulation settings; a
no-pass run stays a no-pass run.
