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


def rotated_mesh(
    data: bytes,
    *,
    axis: tuple[float, float, float],
    origin: tuple[float, float, float],
    angle_deg: float,
) -> Any:
    trimesh = _trimesh()
    mesh = load_mesh(data)
    matrix = trimesh.transformations.rotation_matrix(
        math.radians(angle_deg),
        np.asarray(axis, dtype=float),
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
    samples = first_mesh.triangles_center
    if len(samples) > max_samples:
        samples = samples[:: max(1, len(samples) // max_samples)]
    if len(samples) == 0:
        return False
    inside = second_mesh.contains(samples)
    if not inside.any():
        return False
    depths = ProximityQuery(second_mesh).signed_distance(samples[inside])
    return bool((depths > min_depth_mm).any())


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
    angles = {
        float(joint.get("min_deg", -180.0)),
        0.0,
        float(joint.get("max_deg", 180.0)),
    }
    notes: list[str] = []
    for angle in sorted(angles):
        rotated = rotated_mesh(
            child,
            axis=tuple(joint["axis"]),
            origin=tuple(joint["origin"]),
            angle_deg=angle,
        )
        if meshes_interfere(parent, rotated, min_depth_mm=min_depth_mm):
            notes.append(
                f"parts '{joint['parent']}' and '{joint['child']}' overlap at {angle:.0f} degrees"
            )
    return not notes, notes


__all__ = [
    "INTERFERENCE_DEPTH_MM",
    "articulation_clearance",
    "load_mesh",
    "meshes_interfere",
    "rotated_mesh",
]
