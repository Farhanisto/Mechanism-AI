"""Deterministic geometry and collision checks for four-bar candidates.

The hackathon MVP models the linkage as zero-thickness line segments in a plane.
The ground link is a fixed frame, not a moving body, so it is excluded from
moving-link collision checks. For a four-bar linkage the only non-adjacent pair
of moving links is the crank and the rocker; the coupler shares a pin with each
of them. Link thickness and ground/frame contact are deliberately not modeled.
"""

from collections.abc import Sequence

from app.mechanism.schemas import TraceSample

Point = tuple[float, float]
_EPS = 1e-9


def _cross(origin: Point, first: Point, second: Point) -> float:
    return (first[0] - origin[0]) * (second[1] - origin[1]) - (
        first[1] - origin[1]
    ) * (second[0] - origin[0])


def _on_segment(start: Point, end: Point, point: Point, eps: float = _EPS) -> bool:
    return (
        min(start[0], end[0]) - eps <= point[0] <= max(start[0], end[0]) + eps
        and min(start[1], end[1]) - eps <= point[1] <= max(start[1], end[1]) + eps
        and abs(_cross(start, end, point)) <= eps
    )


def segments_intersect(
    first_start: Point,
    first_end: Point,
    second_start: Point,
    second_end: Point,
    *,
    eps: float = _EPS,
) -> bool:
    """Return True when two closed line segments share any point."""
    d1 = _cross(second_start, second_end, first_start)
    d2 = _cross(second_start, second_end, first_end)
    d3 = _cross(first_start, first_end, second_start)
    d4 = _cross(first_start, first_end, second_end)

    if ((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps)) and (
        (d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps)
    ):
        return True

    return (
        _on_segment(second_start, second_end, first_start, eps)
        or _on_segment(second_start, second_end, first_end, eps)
        or _on_segment(first_start, first_end, second_start, eps)
        or _on_segment(first_start, first_end, second_end, eps)
    )


def has_moving_link_collision(samples: Sequence[TraceSample]) -> bool:
    """Check the crank against the rocker at every sampled pose.

    Adjacent links share a pin, and the ground link is the fixed frame. Those
    contacts are expected and are not collisions for this planar model.
    """
    for sample in samples:
        crank_start = (sample.ground_pivot_a.x, sample.ground_pivot_a.y)
        crank_end = (sample.crank_pin.x, sample.crank_pin.y)
        rocker_start = (sample.ground_pivot_b.x, sample.ground_pivot_b.y)
        rocker_end = (sample.rocker_pin.x, sample.rocker_pin.y)
        if segments_intersect(crank_start, crank_end, rocker_start, rocker_end):
            return True
    return False
