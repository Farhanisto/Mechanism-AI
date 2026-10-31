"""Mesh-space checks for assembly artifacts, independent of the program.

Interference is measured on the exported STL bytes: surface samples of one part
are tested for containment in another, and only penetrations deeper than a
tolerance count (touching faces are allowed). Articulation rotates the child
mesh about the declared joint axis and re-checks the jointed pair.
"""

import io
import math
from typing import Any

import numpy as np

INTERFERENCE_DEPTH_MM = 0.2
MAX_SAMPLES = 300


def _trimesh() -> Any:
    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError(
            "mesh interference checks require the optional CAD dependencies "
            "(`uv sync --extra cad`)"
        ) from exc
    return trimesh


def load_mesh(data: bytes) -> Any:
    trimesh = _trimesh()
    mesh = trimesh.load(io.BytesIO(data), file_type="stl")
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError("the artifact is not a valid triangle mesh")
    return mesh


def transformed_mesh(
    data: bytes,
    *,
    kind: str,
    axis: tuple[float, float, float],
    origin: tuple[float, float, float],
    value: float,
) -> Any:
    """Rotate (revolute) or translate (prismatic) a part about/along a joint."""
    trimesh = _trimesh()
    mesh = load_mesh(data)
    axis_vector = np.asarray(axis, dtype=float)
    norm = float(np.linalg.norm(axis_vector))
    if norm < 1e-9:
        raise ValueError("joint axis must be non-zero")
    unit_axis = axis_vector / norm
    if kind == "prismatic":
        matrix = trimesh.transformations.translation_matrix(unit_axis * value)
    else:
        matrix = trimesh.transformations.rotation_matrix(
            math.radians(value),
            unit_axis,
            point=np.asarray(origin, dtype=float),
        )
    mesh.apply_transform(matrix)
    return mesh


def meshes_interfere(
    first: bytes | Any,
    second: bytes | Any,
    *,
    min_depth_mm: float = INTERFERENCE_DEPTH_MM,
    max_samples: int = MAX_SAMPLES,
) -> bool:
    from trimesh.proximity import ProximityQuery

    first_mesh = load_mesh(first) if isinstance(first, bytes) else first
    second_mesh = load_mesh(second) if isinstance(second, bytes) else second
    def _penetrates(source: Any, target: Any) -> bool:
        samples = source.triangles_center
        if len(samples) > max_samples:
            samples = samples[:: max(1, len(samples) // max_samples)]
        if len(samples) == 0:
            return False
        inside = target.contains(samples)
        if not inside.any():
            return False
        depths = ProximityQuery(target).signed_distance(samples[inside])
        return bool((depths > min_depth_mm).any())

    # Sample both directions: a small part fully inside a larger one has no
    # surface samples of the larger part inside the smaller one.
    return _penetrates(first_mesh, second_mesh) or _penetrates(
        second_mesh, first_mesh
    )


def articulation_clearance(
    parts: dict[str, bytes],
    joint: dict,
    *,
    min_depth_mm: float = INTERFERENCE_DEPTH_MM,
) -> tuple[bool, list[str]]:
    """Rotate the joint's child across its range and check the jointed pair."""
    parent = parts.get(joint["parent"])
    child = parts.get(joint["child"])
    if parent is None or child is None:
        return False, ["joint references a part that was not produced"]
    values = {
        float(joint.get("min_value", -180.0)),
        0.0,
        float(joint.get("max_value", 180.0)),
    }
    notes: list[str] = []
    for value in sorted(values):
        rotated = transformed_mesh(
            child,
            kind=str(joint.get("kind", "revolute")),
            axis=tuple(joint["axis"]),
            origin=tuple(joint["origin"]),
            value=value,
        )
        if meshes_interfere(parent, rotated, min_depth_mm=min_depth_mm):
            unit = "mm" if joint.get("kind", "revolute") == "prismatic" else "degrees"
            notes.append(
                f"parts '{joint['parent']}' and '{joint['child']}' overlap at {value:.0f} {unit}"
            )
    return not notes, notes


__all__ = [
    "INTERFERENCE_DEPTH_MM",
    "articulation_clearance",
    "load_mesh",
    "meshes_interfere",
    "transformed_mesh",
]
