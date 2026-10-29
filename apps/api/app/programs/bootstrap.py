"""Sandbox child process for model-authored design programs.

Executed as a standalone script in an isolated subprocess. It applies resource
limits, installs a restricted import allowlist and a curated builtins namespace,
runs the model-authored source, calls ``build()`` and exports a deterministic
STL next to the request/result manifest.

This is a best-effort sandbox (defense in depth), not a hardened OS boundary:
wall-clock kills, CPU/file-size limits, no inherited secrets, an isolated
working directory and an import allowlist. Do not treat it as a security
boundary for untrusted third-party code.
"""

import hashlib
import json
import math
import os
import re
import sys
import time
import traceback

ALLOWED_MODULES = frozenset({"cadquery", "math", "numpy", "typing"})


def _install_limits(request: dict) -> None:
    import resource

    cpu_seconds = int(request.get("cpu_seconds", 15))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 2))
    max_bytes = int(request.get("max_bytes", 5_000_000))
    resource.setrlimit(resource.RLIMIT_FSIZE, (max_bytes, max_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except (ValueError, OSError):
        pass
    memory_bytes = int(request.get("memory_bytes") or 0)
    if memory_bytes > 0:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except (ValueError, OSError):
            pass


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if root not in ALLOWED_MODULES:
        raise ImportError(f"import of {name!r} is not allowed in design programs")
    return __import__(name, globals, locals, fromlist, level)


def _safe_builtins() -> dict:
    import builtins

    allowed = (
        "abs", "all", "any", "bin", "bool", "bytearray", "bytes", "callable", "chr",
        "classmethod", "complex", "dict", "divmod", "enumerate", "filter", "float",
        "format", "frozenset", "hash", "hex", "id", "int", "isinstance", "issubclass",
        "iter", "len", "list", "map", "max", "min", "next", "object", "oct", "ord",
        "pow", "print", "property", "range", "repr", "reversed", "round", "set",
        "slice", "sorted", "staticmethod", "str", "sum", "super", "tuple", "type",
        "zip", "Exception", "ArithmeticError", "AssertionError", "AttributeError",
        "IndexError", "KeyError", "NotImplementedError", "RuntimeError",
        "StopIteration", "TypeError", "ValueError", "ZeroDivisionError",
        "__build_class__",
    )
    namespace = {name: getattr(builtins, name) for name in allowed}
    namespace["__import__"] = _restricted_import
    return namespace


def main() -> int:
    request_path = sys.argv[1]
    workdir = os.path.dirname(os.path.abspath(request_path))
    os.chdir(workdir)
    with open(request_path, encoding="utf-8") as handle:
        request = json.load(handle)

    result: dict = {
        "status": "failed",
        "error": None,
        "duration_ms": 0.0,
        "size_bytes": 0,
        "sha256": None,
    }
    try:
        _install_limits(request)
        namespace: dict = {
            "__builtins__": _safe_builtins(),
            "__name__": "design_program",
        }
        started = time.perf_counter()
        try:
            exec(compile(request["source"], "<design_program>", "exec"), namespace)
            build = namespace.get("build")
            if not callable(build):
                raise ValueError("the design program must define a callable build()")
            built = build()
        finally:
            result["duration_ms"] = (time.perf_counter() - started) * 1000.0

        import cadquery as cq

        max_bytes = int(request.get("max_bytes", 5_000_000))
        export_options = {
            "tolerance": request.get("tolerance", 0.01),
            "angularTolerance": request.get("angular_tolerance", 0.1),
        }

        def _shape(value: object, label: str):
            if isinstance(value, cq.Workplane):
                value = value.val()
            if not isinstance(value, (cq.Shape, cq.Compound)):
                raise ValueError(
                    f"{label} must be a cadquery Workplane, Shape or Compound"
                )
            return value

        def _vector(value: object, default: tuple[float, float, float]):
            if value is None:
                return list(default)
            if hasattr(value, "toTuple"):
                value = value.toTuple()
            components = list(value)  # type: ignore[arg-type]
            if len(components) != 3:
                raise ValueError("joint vectors must have three components")
            return [float(component) for component in components]

        if isinstance(built, dict):
            raw_parts = built.get("parts")
            if not isinstance(raw_parts, dict) or not raw_parts:
                raise ValueError(
                    "build() must return a shape or a dict with a non-empty 'parts' mapping"
                )
            raw_joints = built.get("joints", [])
            if not isinstance(raw_joints, list):
                raise ValueError("the 'joints' entry must be a list")
        else:
            raw_parts = {"part": built}
            raw_joints = []

        if len(raw_parts) > 12:
            raise ValueError("the assembly exceeds the part budget (max 12)")
        if len(raw_joints) > 6:
            raise ValueError("the assembly exceeds the joint budget (max 6)")

        parts = {}
        for name, value in raw_parts.items():
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,32}", name):
                raise ValueError(f"invalid part name {name!r}")
            parts[name] = _shape(value, f"part {name!r}")

        joints = []
        for index, item in enumerate(raw_joints):
            if not isinstance(item, dict):
                raise ValueError(f"joint {index} must be a dict")
            name = item.get("name")
            parent = item.get("parent")
            child = item.get("child")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,32}", name):
                raise ValueError(f"invalid joint name {name!r}")
            if parent not in parts or child not in parts:
                raise ValueError(f"joint {name!r} references unknown parts")
            if parent == child:
                raise ValueError(f"joint {name!r} must connect two different parts")
            axis = _vector(item.get("axis"), (0.0, 0.0, 1.0))
            if math.sqrt(sum(component * component for component in axis)) < 1e-9:
                raise ValueError(f"joint {name!r} needs a non-zero axis")
            joints.append(
                {
                    "name": name,
                    "parent": parent,
                    "child": child,
                    "origin": _vector(item.get("origin"), (0.0, 0.0, 0.0)),
                    "axis": axis,
                    "min_deg": float(item.get("min_deg", -180.0)),
                    "max_deg": float(item.get("max_deg", 180.0)),
                }
            )

        part_records = []
        for name, shape in parts.items():
            part_path = os.path.join(workdir, f"part_{name}.stl")
            cq.exporters.export(shape, part_path, exportType="STL", opt=export_options)
            with open(part_path, "rb") as handle:
                part_data = handle.read()
            if not part_data:
                raise ValueError(f"part {name!r} exported an empty mesh")
            if len(part_data) > max_bytes:
                raise ValueError(f"part {name!r} exceeds the size budget")
            part_records.append(
                {
                    "name": name,
                    "sha256": hashlib.sha256(part_data).hexdigest(),
                    "size_bytes": len(part_data),
                }
            )

        compound = cq.Compound.makeCompound(list(parts.values()))
        stl_path = os.path.join(workdir, "output.stl")
        cq.exporters.export(compound, stl_path, exportType="STL", opt=export_options)
        with open(stl_path, "rb") as handle:
            data = handle.read()
        if not data:
            raise ValueError("the design program exported an empty mesh")
        if len(data) > max_bytes:
            raise ValueError("the exported mesh exceeds the size budget")
        result.update(
            status="executed",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            parts=part_records,
            joints=joints,
        )
    except BaseException as exc:  # noqa: BLE001 - report every failure honestly
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
        result["traceback"] = traceback.format_exc(limit=5)[-1000:]
        result["status"] = "failed"

    with open(os.path.join(workdir, "result.json"), "w", encoding="utf-8") as handle:
        json.dump(result, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
