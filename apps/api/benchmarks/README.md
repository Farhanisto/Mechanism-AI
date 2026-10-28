# Benchmarks

Machine-readable benchmark fixtures with manually reviewed expected outcomes.
They run as part of the normal suite (`uv run pytest tests/test_benchmark.py`) and
under both simulation engines (CI runs them with MuJoCo and with the reference
solver only).

## Evaluator benchmark (`evaluator_benchmark.json`)

Classification cases for the independent evaluator. Each case pairs a typed
candidate with a brief and states the expected evaluation status and failed
constraints, justified in the case `rationale`.

| id | category | expected | measured (travel / footprint / trajectory) |
| --- | --- | --- | --- |
| c1_demo_pass | passing | passed | 99.51 / 181.97 / 4.14 mm |
| c2_demo_pass_near_limit | boundary | passed | 98.89 / 183.99 / 4.70 mm |
| c3_demo_pass | passing | passed | 101.30 / 170.00 / 4.63 mm |
| c4_demo_fail_travel | failing | failed `travel_distance` | 84.22 / 151.50 / 4.04 mm |
| c4_target84_pass | boundary | passed | 84.22 / 151.50 / 4.04 mm |
| c4_target84_tight_tolerance | boundary | failed `trajectory_tolerance` | 84.22 / 151.50 / 4.04 mm |
| c1_tight_footprint | failing | failed `max_footprint` | 99.51 / 181.97 / 4.14 mm |
| c1_tight_tolerance | failing | failed `trajectory_tolerance` | 99.51 / 181.97 / 4.14 mm |
| c1_contradictory_brief | failing | failed `travel_distance`, `max_footprint` | 99.51 / 181.97 / 4.14 mm |
| c7_partial_cycle | failing | failed `travel_distance`, `complete_motion_cycle` | 85.80 / 181.97 / 4.62 mm |
| c8_moving_link_collision | failing | failed incl. `avoid_collisions` | 320.00 / 359.99 / 97.00 mm |
| c5_unclosable_mid_cycle | invalid | failed incl. `simulation_integrity` | invalid simulation |
| c6_unclosable_at_start | invalid | failed incl. `simulation_integrity` | invalid simulation |

Results (2026-10-29):

- Classification accuracy: **13/13 correct (100%)** — target AC-01 is at least 90%.
- Known false passes: **0** — target AC-02 is zero; every reviewed failure
  (including the boundary and contradictory cases) is classified `failed`, and
  only reviewed passing cases are classified `passed`.
- Reference and MuJoCo engines produce identical classifications; measured
  metrics agree within the documented 0.05 mm reference-comparison tolerance.

## Repair benchmark (`repair_benchmark.json`)

Scripted candidate sequences that exercise the bounded repair loop under the
unchanged evaluator.

| id | category | expected outcome | attempts |
| --- | --- | --- | --- |
| passes_first_try | baseline | passed | 1 |
| repair_in_one_attempt | repairable | passed | 2 |
| repair_in_two_attempts | repairable | passed | 3 |
| not_repairable_exhausted | not_repairable | no_pass (best: candidate_001) | 3 |
| invalid_output_during_repair | failure_path | run_failed `INVALID_MODEL_OUTPUT` | — |

Results (2026-10-29):

- Repair success on deliberately repairable cases: **2/2 (100%)** within three
  total candidates — target AC-03 is at least 70%.
- Exhausted budgets end as `no_pass: true` with best-candidate reporting
  (fewest failed constraints), never an error or a fake success.
- Schema-invalid model output during repair fails the run explicitly.

## What these benchmarks do and do not measure

- They validate the repair **path**: the loop consumes evaluator feedback,
  stays inside the three-candidate budget, judges every revision with the same
  fixed evaluator, and reports honestly when repair fails. The candidate
  sequences are scripted, so the success rate measures pipeline mechanics, not
  the creative quality of a live model.
- Live-model repair quality (AC-03 against a real provider) is measured
  manually with `MECHANISM_AI_META_API_KEY` set: run the deliberately repairable
  prompts and record how often a pass is reached within three candidates.
- Classification accuracy here is against hand-reviewed outcomes; the PRD's
  broader benchmark suite should add independently reviewed cases over time.

## Assumptions carried by these fixtures

- Links are zero-thickness line segments; the ground link is a fixed frame;
  only crank-vs-rocker segment intersections count as collisions.
- Evaluator v0.1.0 uses `trajectory_tolerance` for both travel-distance error
  and path deviation; thresholds are inclusive (`<=`).
- `cycle_completed` requires a closed trace over at least a 360-degree input
  span; partial sweeps fail `complete_motion_cycle` when the brief requires it.
- Simulation integrity failures zero the metrics and fail every motion-related
  check, so an invalid simulation can never look like a pass.
- Run-level `no_pass` is produced when every candidate fails; it is a completed
  run outcome, not an error.
