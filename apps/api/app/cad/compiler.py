"""Deterministic CadQuery/OpenCascade compiler for typed design plans.

The compiler only executes whitelisted operations on typed parameters. Plan
documents are data; a plan can never inject code, shell commands or arbitrary
geometry operations. Exports are tessellated with fixed tolerances so the same
plan and compiler version produce byte-identical STL output.
"""

import hashlib
import math
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.cad.plan import (
    CAPABILITY_ID,
    CAPABILITY_VERSION,
    SUPPORTED_OPERATIONS,
    InvalidPlanError,
)
from app.mechanism.schemas import DesignPlan, GeometryArtifact, Units

COMPILER_VERSION = "0.1.0"
MAX_COMPONENTS = 8
MAX_EXPORT_BYTES = 5_000_000
TESSELATION_TOLERANCE_MM = 0.01
ANGULAR_TOLERANCE_RAD = 0.1
_MAX_LINK_LENGTH_MM = 10_000.0
_GEOMETRY_SLACK_MM = 0.6

_REQUIRED_PARAMETERS = (
    "length",
    "width",
    "thickness",
    "pin_hole_diameter",
    "start_x",
    "start_y",
    "end_x",
    "end_y",
)


class CadNotAvailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CompiledGeometry:
    artifact: GeometryArtifact
    data: bytes


def is_cad_available() -> bool:
    try:
        import cadquery  # noqa: F401
    except ImportError:
        return False
    return True


def _load_cadquery() -> Any:
    try:
        import cadquery
    except ImportError as exc:
        raise CadNotAvailable(
            "CadQuery is not installed. Install the optional dependencies with "
            "`uv sync --extra cad` to generate geometry artifacts."
        ) from exc
    return cadquery


def _validate_plan(plan: DesignPlan) -> None:
    if plan.capability_id != CAPABILITY_ID:
        raise InvalidPlanError(f"unsupported capability {plan.capability_id!r}")
    if plan.capability_version != CAPABILITY_VERSION:
        raise InvalidPlanError(
            f"unsupported capability version {plan.capability_version!r}"
        )
    if len(plan.components) > MAX_COMPONENTS:
        raise InvalidPlanError("the plan exceeds the component budget")

    component_ids = {component.component_id for component in plan.components}
    if len(component_ids) != len(plan.components):
        raise InvalidPlanError("component ids must be unique")

    for operation in plan.geometry_operations:
        if operation.operation not in SUPPORTED_OPERATIONS:
            raise InvalidPlanError(
                f"unsupported geometry operation {operation.operation!r}"
            )
        if operation.component_id is not None and operation.component_id not in component_ids:
            raise InvalidPlanError(
                f"operation references unknown component {operation.component_id!r}"
            )

    for joint in plan.joints:
        if joint.kind != "revolute":
            raise InvalidPlanError(f"unsupported joint kind {joint.kind!r}")
        if joint.parent not in component_ids or joint.child not in component_ids:
            raise InvalidPlanError(f"joint {joint.joint_id!r} references unknown components")

    for component in plan.components:
        if component.kind != "link":
            raise InvalidPlanError(f"unsupported component kind {component.kind!r}")
        missing = [name for name in _REQUIRED_PARAMETERS if name not in component.parameters]
        if missing:
            raise InvalidPlanError(
                f"component {component.component_id!r} is missing parameters: {missing}"
            )
        parameters = component.parameters
        for name in _REQUIRED_PARAMETERS:
            value = parameters[name]
            if not math.isfinite(value):
                raise InvalidPlanError(
                    f"component {component.component_id!r} parameter {name!r} is not finite"
                )
        length = parameters["length"]
        width = parameters["width"]
        thickness = parameters["thickness"]
        hole = parameters["pin_hole_diameter"]
        if not 0.0 < length <= _MAX_LINK_LENGTH_MM:
            raise InvalidPlanError("link length is outside the supported range")
        if not hole < width <= _MAX_LINK_LENGTH_MM:
            raise InvalidPlanError("link width must exceed the pin hole diameter")
        if not 0.0 < thickness <= 100.0:
            raise InvalidPlanError("link thickness is outside the supported range")
        if length < 2.0 * hole:
            raise InvalidPlanError("link length is too short for its pin holes")
        span = math.hypot(
            parameters["end_x"] - parameters["start_x"],
            parameters["end_y"] - parameters["start_y"],
        )
        if abs(span - length) > 0.01:
            raise InvalidPlanError(
                f"component {component.component_id!r} geometry does not match its length"
            )


def _mesh_stats(data: bytes) -> tuple[int, tuple[float, float, float, float], float]:
    if len(data) < 84:
        raise InvalidPlanError("the exported mesh is empty")
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + triangle_count * 50:
        raise InvalidPlanError("the exported mesh is malformed")

    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    volume = 0.0
    for index in range(triangle_count):
        offset = 84 + index * 50 + 12
        vertices = struct.unpack_from("<9f", data, offset)
        x0, y0, z0 = vertices[0], vertices[1], vertices[2]
        x1, y1, z1 = vertices[3], vertices[4], vertices[5]
        x2, y2, z2 = vertices[6], vertices[7], vertices[8]
        min_x, max_x = min(min_x, x0, x1, x2), max(max_x, x0, x1, x2)
        min_y, max_y = min(min_y, y0, y1, y2), max(max_y, y0, y1, y2)
        volume += (
            x0 * (y1 * z2 - z1 * y2)
            - y0 * (x1 * z2 - z1 * x2)
            + z0 * (x1 * y2 - y1 * x2)
        ) / 6.0
    return triangle_count, (min_x, min_y, max_x, max_y), volume


def _export_stl(cq: Any, compound: Any) -> bytes:
    handle, path = tempfile.mkstemp(suffix=".stl")
    os.close(handle)
    try:
        cq.exporters.export(
            compound,
            path,
            exportType="STL",
            opt={
                "tolerance": TESSELATION_TOLERANCE_MM,
                "angularTolerance": ANGULAR_TOLERANCE_RAD,
            },
        )
        return Path(path).read_bytes()
    finally:
        if os.path.exists(path):
            os.unlink(path)


def compile_plan(plan: DesignPlan, *, artifact_id: str) -> CompiledGeometry:
    """Compile a typed plan into a deterministic STL geometry artifact."""
    cq = _load_cadquery()
    _validate_plan(plan)

    solids = []
    for component in plan.components:
        parameters = component.parameters
        length = parameters["length"]
        width = parameters["width"]
        thickness = parameters["thickness"]
        hole = parameters["pin_hole_diameter"]
        bar_length = length + hole
        body = (
            cq.Workplane("XY")
            .box(bar_length, width, thickness)
            .faces(">Z")
            .workplane()
            .pushPoints([(-length / 2.0, 0.0), (length / 2.0, 0.0)])
            .hole(hole)
        )
        angle_deg = math.degrees(
            math.atan2(
                parameters["end_y"] - parameters["start_y"],
                parameters["end_x"] - parameters["start_x"],
            )
        )
        mid_x = (parameters["start_x"] + parameters["end_x"]) / 2.0
        mid_y = (parameters["start_y"] + parameters["end_y"]) / 2.0
        solids.append(
            body.rotate((0, 0, 0), (0, 0, 1), angle_deg).translate((mid_x, mid_y, 0.0))
        )

    compound = cq.Compound.makeCompound([solid.val() for solid in solids])
    data = _export_stl(cq, compound)
    artifact_hash = hashlib.sha256(data).hexdigest()

    triangle_count, (min_x, min_y, max_x, max_y), volume = _mesh_stats(data)
    joints_inside = all(
        min_x - _GEOMETRY_SLACK_MM <= joint.origin[0] <= max_x + _GEOMETRY_SLACK_MM
        and min_y - _GEOMETRY_SLACK_MM <= joint.origin[1] <= max_y + _GEOMETRY_SLACK_MM
        for joint in plan.joints
    )
    budget = min(
        plan.resource_budget.get("max_export_bytes", MAX_EXPORT_BYTES),
        MAX_EXPORT_BYTES,
    )
    validation_results = {
        "mesh_non_empty": triangle_count > 0,
        "joints_inside_bounding_box": joints_inside,
        "closed_volume": volume > 0.0,
        "size_within_budget": len(data) <= budget,
    }
    failed = [name for name, ok in validation_results.items() if not ok]
    artifact = GeometryArtifact(
        artifact_id=artifact_id,
        format="stl",
        units=Units.MM,
        compiler_version=COMPILER_VERSION,
        generation_status="failed" if failed else "generated",
        validation_results=validation_results,
        artifact_hash=artifact_hash,
        error=(
            "geometry validation failed: " + ", ".join(failed) if failed else None
        ),
    )
    return CompiledGeometry(artifact=artifact, data=data)


__all__ = [
    "ANGULAR_TOLERANCE_RAD",
    "COMPILER_VERSION",
    "CadNotAvailable",
    "CompiledGeometry",
    "MAX_EXPORT_BYTES",
    "TESSELATION_TOLERANCE_MM",
    "compile_plan",
    "is_cad_available",
]
