"""Deterministic planar four-bar kinematics for the reference simulation.

Conventions:
- Ground pivots are ``O2 = (0, 0)`` and ``O4 = (ground_length, 0)``.
- The input angle is measured counter-clockwise from the +x axis.
- The output point is the rocker pin ``B``. Measurements are in millimetres.
- Sampling is kinematic, not dynamic; ``time_s`` is normalized cycle time.

The solver keeps a fixed assembly branch for the whole trace. If the linkage
cannot close on that branch at any sampled input angle, the trace is invalid
rather than silently switching branches.
"""

import math

from pydantic import ValidationError

from app.evaluation.geometry_checks import has_moving_link_collision
from app.mechanism.schemas import (
    Candidate,
    Point2D,
    SimulationResult,
    TraceSample,
)

ENGINE_NAME = "reference_kinematics"
ENGINE_VERSION = "0.1.0"
DEFAULT_SAMPLE_COUNT = 361
_CYCLE_DEGREES = 360.0
_EPS = 1e-9
_MAX_COORDINATE = 1_000_000.0

Point = tuple[float, float]


class KinematicsError(ValueError):
    """Raised when a trace cannot be produced for an invalid solver request."""


def _solve_rocker_pin(
    crank_pin: Point,
    ground_pivot_b: Point,
    coupler_length: float,
    rocker_length: float,
) -> tuple[Point, Point] | None:
    """Intersect the coupler circle around A with the rocker circle around O4."""
    dx = ground_pivot_b[0] - crank_pin[0]
    dy = ground_pivot_b[1] - crank_pin[1]
    distance = math.hypot(dx, dy)
    if distance <= _EPS:
        return None
    if distance > coupler_length + rocker_length + _EPS:
        return None
    if distance < abs(coupler_length - rocker_length) - _EPS:
        return None

    along = (coupler_length**2 - rocker_length**2 + distance**2) / (2.0 * distance)
    height_sq = coupler_length**2 - along**2
    if height_sq < -_EPS:
        return None
    height = math.sqrt(max(0.0, height_sq))

    midpoint = (
        crank_pin[0] + along * dx / distance,
        crank_pin[1] + along * dy / distance,
    )
    offset = (-dy * height / distance, dx * height / distance)
    return (
        (midpoint[0] + offset[0], midpoint[1] + offset[1]),
        (midpoint[0] - offset[0], midpoint[1] - offset[1]),
    )


def _point(point: Point) -> Point2D:
    x, y = point
    if not (math.isfinite(x) and math.isfinite(y)):
        raise KinematicsError("non-finite joint coordinate")
    if abs(x) > _MAX_COORDINATE or abs(y) > _MAX_COORDINATE:
        raise KinematicsError("joint coordinate exceeded the simulation bound")
    return Point2D(x=x, y=y)


def simulate_four_bar(
    candidate: Candidate,
    *,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    engine: str = ENGINE_NAME,
    engine_version: str = ENGINE_VERSION,
) -> SimulationResult:
    """Sample a candidate over its requested input range on one assembly branch."""
    if sample_count < 2:
        raise KinematicsError("sample_count must be at least 2")

    parameters = candidate.parameters
    ground_pivot_a: Point = (0.0, 0.0)
    ground_pivot_b: Point = (parameters.ground_length, 0.0)
    start_angle = candidate.input_motion.start_angle_deg
    end_angle = candidate.input_motion.end_angle_deg
    span = end_angle - start_angle

    samples: list[TraceSample] = []
    failure_reason: str | None = None
    branch: int | None = None

    for index in range(sample_count):
        fraction = index / (sample_count - 1)
        input_angle = start_angle + span * fraction
        radians = math.radians(input_angle)
        crank_pin: Point = (
            parameters.crank_length * math.cos(radians),
            parameters.crank_length * math.sin(radians),
        )
        intersections = _solve_rocker_pin(
            crank_pin,
            ground_pivot_b,
            parameters.coupler_length,
            parameters.rocker_length,
        )
        if intersections is None:
            failure_reason = (
                f"linkage cannot close on the selected branch at "
                f"{input_angle:.2f} degrees"
            )
            break

        first, second = intersections
        if branch is None:
            branch = 1 if first[1] >= second[1] else -1
        rocker_pin = first if branch == 1 else second

        try:
            samples.append(
                TraceSample(
                    time_s=fraction,
                    input_angle_deg=input_angle,
                    ground_pivot_a=_point(ground_pivot_a),
                    ground_pivot_b=_point(ground_pivot_b),
                    crank_pin=_point(crank_pin),
                    rocker_pin=_point(rocker_pin),
                    output_point=_point(rocker_pin),
                )
            )
        except (KinematicsError, ValidationError) as exc:
            failure_reason = str(exc)
            break

    simulation_valid = failure_reason is None and bool(samples)
    cycle_completed = False
    if simulation_valid and abs(span) >= _CYCLE_DEGREES - _EPS:
        first_output = samples[0].output_point
        last_output = samples[-1].output_point
        closure_error = math.hypot(
            last_output.x - first_output.x,
            last_output.y - first_output.y,
        )
        cycle_completed = closure_error <= 1e-6

    collision_free = (
        simulation_valid
        and bool(samples)
        and not has_moving_link_collision(samples)
    )

    return SimulationResult(
        candidate_id=candidate.candidate_id,
        engine=engine,
        engine_version=engine_version,
        samples=samples,
        cycle_completed=cycle_completed,
        collision_free=collision_free,
        simulation_valid=simulation_valid,
        failure_reason=failure_reason,
    )
