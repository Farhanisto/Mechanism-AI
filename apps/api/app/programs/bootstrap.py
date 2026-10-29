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
import os
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
            shape = build()
        finally:
            result["duration_ms"] = (time.perf_counter() - started) * 1000.0

        import cadquery as cq

        if isinstance(shape, cq.Workplane):
            shape = shape.val()
        if not isinstance(shape, (cq.Shape, cq.Compound)):
            raise ValueError("build() must return a cadquery Workplane, Shape or Compound")
        stl_path = os.path.join(workdir, "output.stl")
        cq.exporters.export(
            shape,
            stl_path,
            exportType="STL",
            opt={
                "tolerance": request.get("tolerance", 0.01),
                "angularTolerance": request.get("angular_tolerance", 0.1),
            },
        )
        with open(stl_path, "rb") as handle:
            data = handle.read()
        if not data:
            raise ValueError("the design program exported an empty mesh")
        if len(data) > int(request.get("max_bytes", 5_000_000)):
            raise ValueError("the exported mesh exceeds the size budget")
        result.update(
            status="executed",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
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
