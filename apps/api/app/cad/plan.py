"""Typed design plans for the four-bar link-set capability.

Plans are declarative data: components, joints, geometry operations and the
assembly pose. They contain no code; only whitelisted operations compiled by
``app.cad.compiler`` are ever executed.
"""

import math

from app.mechanism.kinematics import solve_rocker_pin
from app.mechanism.schemas import (
    Candidate,
    DesignPlan,
    PlanComponent,
    PlanGeometryOp,
    PlanJoint,
)

CAPABILITY_ID = "four_bar_linkage"
CAPABILITY_VERSION = "0.1.0"

LINK_WIDTH_MM = 12.0
LINK_THICKNESS_MM = 4.0
PIN_HOLE_DIAMETER_MM = 6.0
SUPPORTED_OPERATIONS = ("extrude_link",)


class InvalidPlanError(ValueError):
    """Raised when a design plan is malformed or cannot be assembled."""


def _joint_positions(candidate: Candidate) -> dict[str, tuple[float, float]]:
    parameters = candidate.parameters
    start = math.radians(candidate.input_motion.start_angle_deg)
    o2 = (0.0, 0.0)
    o4 = (parameters.ground_length, 0.0)
    a = (
        parameters.crank_length * math.cos(start),
        parameters.crank_length * math.sin(start),
    )
    intersections = solve_rocker_pin(
        a, o4, parameters.coupler_length, parameters.rocker_length
    )
    if intersections is None:
        raise InvalidPlanError(
            "the linkage cannot be assembled at the requested start angle"
        )
    first, second = intersections
    b = first if first[1] >= second[1] else second
    return {"o2": o2, "a": a, "b": b, "o4": o4}


def plan_from_candidate(candidate: Candidate) -> DesignPlan:
    """Build the deterministic link-set plan for a validated candidate."""
    parameters = candidate.parameters
    joints = _joint_positions(candidate)
    links = (
        ("ground_link", joints["o2"], joints["o4"], parameters.ground_length),
        ("crank_link", joints["o2"], joints["a"], parameters.crank_length),
        ("coupler_link", joints["a"], joints["b"], parameters.coupler_length),
        ("rocker_link", joints["o4"], joints["b"], parameters.rocker_length),
    )
    components = [
        PlanComponent(
            component_id=component_id,
            kind="link",
            parameters={
                "length": length,
                "width": LINK_WIDTH_MM,
                "thickness": LINK_THICKNESS_MM,
                "pin_hole_diameter": PIN_HOLE_DIAMETER_MM,
                "start_x": start[0],
                "start_y": start[1],
                "end_x": end[0],
                "end_y": end[1],
            },
        )
        for component_id, start, end, length in links
    ]
    joints_spec = (
        ("o2_joint", "ground_link", "crank_link", joints["o2"]),
        ("a_joint", "crank_link", "coupler_link", joints["a"]),
        ("b_joint", "coupler_link", "rocker_link", joints["b"]),
        ("o4_joint", "rocker_link", "ground_link", joints["o4"]),
    )
    plan_joints = [
        PlanJoint(
            joint_id=joint_id,
            kind="revolute",
            parent=parent,
            child=child,
            origin=(position[0], position[1], 0.0),
        )
        for joint_id, parent, child, position in joints_spec
    ]
    return DesignPlan(
        capability_id=CAPABILITY_ID,
        capability_version=CAPABILITY_VERSION,
        components=components,
        joints=plan_joints,
        geometry_operations=[
            PlanGeometryOp(operation="extrude_link", component_id=component.component_id)
            for component in components
        ],
        required_checks=[
            "mesh_non_empty",
            "joints_inside_bounding_box",
            "closed_volume",
        ],
        resource_budget={
            "max_components": 8.0,
            "max_export_bytes": 5_000_000.0,
        },
    )
