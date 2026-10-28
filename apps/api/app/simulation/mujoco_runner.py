"""MuJoCo closed-loop runner for compiled four-bar candidates.

The compiled model closes the loop with a ``connect`` equality between the
coupler end and the rocker tip. The input crank is driven kinematically: at
every sample the crank joint is pinned at the commanded angle and the loop is
settled with bounded simulation steps before the state is sampled. All
per-candidate problems — invalid parameters, engine errors, non-finite states
and broken loop closure — are reported as structured simulation failures
instead of crashes.
"""

import math
from typing import Any

from app.evaluation.geometry_checks import has_moving_link_collision
from app.mechanism.compiler import InvalidCandidateError, compile_candidate
from app.mechanism.kinematics import DEFAULT_SAMPLE_COUNT
from app.mechanism.schemas import (
    Candidate,
    Point2D,
    SimulationDiagnostics,
    SimulationResult,
    TraceSample,
)

ENGINE_NAME = "mujoco"
TIMESTEP_S = 1e-3
SETTLE_TARGET_MM = 1e-4
SETTLE_STEP_LIMIT = 200
LOOP_CLOSURE_LIMIT_MM = 0.05
CYCLE_CLOSURE_LIMIT_MM = 1e-2
_FULL_CYCLE_DEGREES = 360.0
_EPS = 1e-9


class SimulationNotAvailable(RuntimeError):
    pass


def is_mujoco_available() -> bool:
    try:
        import mujoco  # noqa: F401
    except ImportError:
        return False
    return True


def _load_mujoco() -> Any:
    try:
        import mujoco
    except ImportError as exc:
        raise SimulationNotAvailable(
            "MuJoCo is not installed. Install the optional dependencies with "
            "`uv sync --extra sim` or run with the reference engine."
        ) from exc
    return mujoco


def _failure(
    candidate: Candidate,
    engine_version: str,
    diagnostics: SimulationDiagnostics | None,
    samples: list[TraceSample],
    reason: str,
) -> SimulationResult:
    return SimulationResult(
        candidate_id=candidate.candidate_id,
        engine=ENGINE_NAME,
        engine_version=engine_version,
        samples=samples,
        simulation_valid=False,
        failure_reason=reason,
        diagnostics=diagnostics,
    )


def run_mujoco_simulation(
    candidate: Candidate,
    *,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
) -> SimulationResult:
    """Run a compiled candidate and record bounded-interval state samples."""
    mujoco = _load_mujoco()
    engine_version = mujoco.__version__

    try:
        compiled = compile_candidate(candidate)
    except InvalidCandidateError as exc:
        return _failure(
            candidate, engine_version, None, [], f"invalid candidate: {exc}"
        )

    diagnostics = SimulationDiagnostics(
        compiler_version=compiled.compiler_version,
        solver="Newton",
        timestep_s=TIMESTEP_S,
        settle_target_mm=SETTLE_TARGET_MM,
        settle_step_limit=SETTLE_STEP_LIMIT,
    )

    try:
        model = mujoco.MjModel.from_xml_string(compiled.mjcf_xml)
        data = mujoco.MjData(model)
    except Exception as exc:
        return _failure(
            candidate,
            engine_version,
            diagnostics,
            [],
            f"the compiled model could not be loaded: {exc}",
        )

    model.opt.timestep = TIMESTEP_S
    crank_qpos = model.joint("crank_hinge").qposadr[0]
    coupler_end = model.site("coupler_end").id
    rocker_tip = model.site("rocker_tip").id
    ground_pivot_a = model.site("ground_pivot_a").id
    ground_pivot_b = model.site("ground_pivot_b").id
    crank_pin = model.site("crank_pin").id

    start_angle = candidate.input_motion.start_angle_deg
    span = candidate.input_motion.end_angle_deg - start_angle

    samples: list[TraceSample] = []
    failure_reason: str | None = None
    max_closure_mm = 0.0
    max_settle_steps = 0
    max_solver_iterations = 0
    max_contacts = 0

    for index in range(sample_count):
        fraction = index / (sample_count - 1)
        input_angle = start_angle + span * fraction
        target = math.radians(span) * fraction
        settle_steps = 0
        closure_m = 0.0
        for step in range(1, SETTLE_STEP_LIMIT + 1):
            data.qpos[crank_qpos] = target
            data.qvel[crank_qpos] = 0.0
            mujoco.mj_step(model, data)
            settle_steps = step
            coupler_pos = data.site_xpos[coupler_end]
            rocker_pos = data.site_xpos[rocker_tip]
            closure_m = math.dist(coupler_pos, rocker_pos)
            if not math.isfinite(closure_m):
                failure_reason = (
                    f"the simulation produced a non-finite state at "
                    f"{input_angle:.2f} degrees"
                )
                break
            if closure_m * 1000.0 < SETTLE_TARGET_MM:
                break
        if failure_reason is not None:
            break

        closure_mm = closure_m * 1000.0
        max_closure_mm = max(max_closure_mm, closure_mm)
        max_settle_steps = max(max_settle_steps, settle_steps)
        max_solver_iterations = max(
            max_solver_iterations, int(max(data.solver_niter))
        )
        max_contacts = max(max_contacts, int(data.ncon))

        if closure_mm > LOOP_CLOSURE_LIMIT_MM:
            failure_reason = (
                f"the loop closure error {closure_mm:.3f} mm exceeded the "
                f"{LOOP_CLOSURE_LIMIT_MM:.3f} mm limit at {input_angle:.2f} degrees"
            )
            break

        point = data.site_xpos[rocker_tip]
        try:
            output = Point2D(x=point[0] * 1000.0, y=point[1] * 1000.0)
            samples.append(
                TraceSample(
                    time_s=fraction,
                    input_angle_deg=input_angle,
                    ground_pivot_a=Point2D(
                        x=data.site_xpos[ground_pivot_a][0] * 1000.0,
                        y=data.site_xpos[ground_pivot_a][1] * 1000.0,
                    ),
                    ground_pivot_b=Point2D(
                        x=data.site_xpos[ground_pivot_b][0] * 1000.0,
                        y=data.site_xpos[ground_pivot_b][1] * 1000.0,
                    ),
                    crank_pin=Point2D(
                        x=data.site_xpos[crank_pin][0] * 1000.0,
                        y=data.site_xpos[crank_pin][1] * 1000.0,
                    ),
                    rocker_pin=output,
                    output_point=output,
                )
            )
        except ValueError as exc:
            failure_reason = str(exc)
            break

    diagnostics.max_loop_closure_error_mm = max_closure_mm
    diagnostics.max_settle_steps_used = max_settle_steps
    diagnostics.max_solver_iterations = max_solver_iterations
    diagnostics.max_contacts = max_contacts

    if failure_reason is not None:
        return _failure(
            candidate, engine_version, diagnostics, samples, failure_reason
        )

    simulation_valid = bool(samples)
    cycle_completed = False
    if simulation_valid and abs(span) >= _FULL_CYCLE_DEGREES - _EPS:
        first_output = samples[0].output_point
        last_output = samples[-1].output_point
        cycle_error = math.hypot(
            last_output.x - first_output.x, last_output.y - first_output.y
        )
        cycle_completed = cycle_error <= CYCLE_CLOSURE_LIMIT_MM

    collision_free = simulation_valid and not has_moving_link_collision(samples)

    return SimulationResult(
        candidate_id=candidate.candidate_id,
        engine=ENGINE_NAME,
        engine_version=engine_version,
        samples=samples,
        cycle_completed=cycle_completed,
        collision_free=collision_free,
        simulation_valid=simulation_valid,
        diagnostics=diagnostics,
    )
