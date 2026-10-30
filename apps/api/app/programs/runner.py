"""Sandboxed execution of model-authored design programs.

The model writes CadQuery Python; this module executes it in an isolated
subprocess (see ``bootstrap.py``) with bounded time, file size and memory, a
module allowlist and a curated builtins namespace. The resulting STL mesh is
validated here, independently of the program that produced it.

Security posture: this is a best-effort sandbox for model output, not a
hardened OS boundary. Static denies, the import allowlist and resource limits
reduce risk; production use should run the sandbox in a container without
network access or secrets.
"""

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.cad.compiler import MeshStats, mesh_stats
from app.mechanism.schemas import DesignProgram, ProgramJoint

SANDBOX_VERSION = "0.1.0"
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_MEMORY_BYTES = 0
TESSELATION_TOLERANCE_MM = 0.01
ANGULAR_TOLERANCE_RAD = 0.1
MAX_SOURCE_LENGTH = 20_000

_FORBIDDEN_SNIPPETS = (
    "__",
    "open(",
    "eval(",
    "exec(",
    "compile(",
    "subprocess",
    "socket",
    "ctypes",
    "shutil",
    "pathlib",
    "importlib",
    "requests",
    "urllib",
    "os.",
    "sys.",
    "builtins",
    "pickle",
    "marshal",
    "inspect",
    "input(",
)

_BOOTSTRAP = Path(__file__).with_name("bootstrap.py")


class ProgramRejectedError(ValueError):
    """Raised when a program fails the static safety checks before execution."""


@dataclass(frozen=True)
class ProgramPartExecution:
    name: str
    stl: bytes
    sha256: str
    stats: MeshStats


@dataclass(frozen=True)
class ProgramExecution:
    status: str
    stl: bytes | None
    sha256: str | None
    duration_ms: float
    error: str | None
    stdout: str
    stats: MeshStats | None
    parts: tuple[ProgramPartExecution, ...] = ()
    joints: tuple[ProgramJoint, ...] = ()


def _failure(duration_ms: float, stdout: str, message: str) -> ProgramExecution:
    return ProgramExecution(
        status="failed",
        stl=None,
        sha256=None,
        duration_ms=duration_ms,
        error=message,
        stdout=stdout,
        stats=None,
    )


def static_check(program: DesignProgram) -> None:
    source = program.source
    if len(source) > MAX_SOURCE_LENGTH:
        raise ProgramRejectedError("the design program exceeds the source size limit")
    lowered = source.lower()
    for snippet in _FORBIDDEN_SNIPPETS:
        if snippet in lowered:
            raise ProgramRejectedError(
                f"the design program uses a forbidden construct ({snippet!r})"
            )
    if "def build" not in lowered:
        raise ProgramRejectedError("the design program must define build()")


def run_design_program(
    program: DesignProgram,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    memory_bytes: int = DEFAULT_MEMORY_BYTES,
) -> ProgramExecution:
    """Execute a design program in the sandbox and validate its STL output."""
    static_check(program)
    with tempfile.TemporaryDirectory(prefix="mechanism-program-") as workspace:
        request_path = Path(workspace) / "request.json"
        request_path.write_text(
            json.dumps(
                {
                    "source": program.source,
                    "entrypoint": program.entrypoint,
                    "cpu_seconds": int(timeout_seconds),
                    "max_bytes": max_bytes,
                    "memory_bytes": memory_bytes,
                    "tolerance": TESSELATION_TOLERANCE_MM,
                    "angular_tolerance": ANGULAR_TOLERANCE_RAD,
                }
            ),
            encoding="utf-8",
        )
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": workspace,
            "TMPDIR": workspace,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(_BOOTSTRAP), str(request_path)],
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds + 5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ProgramExecution(
                status="timeout",
                stl=None,
                sha256=None,
                duration_ms=(timeout_seconds + 5) * 1000.0,
                error="the design program exceeded its wall-clock budget",
                stdout="",
                stats=None,
            )

        stdout = (completed.stdout or "")[-2000:]
        result_path = Path(workspace) / "result.json"
        if not result_path.is_file():
            if completed.returncode is not None and completed.returncode < 0:
                reason = "the sandbox was terminated by a resource limit"
            else:
                reason = "the sandbox produced no result manifest"
            return ProgramExecution(
                status="failed",
                stl=None,
                sha256=None,
                duration_ms=0.0,
                error=reason
                + (f" (stderr: {completed.stderr[-300:]})" if completed.stderr else ""),
                stdout=stdout,
                stats=None,
            )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        duration_ms = float(result.get("duration_ms") or 0.0)
        if result.get("status") != "executed":
            return ProgramExecution(
                status="failed",
                stl=None,
                sha256=None,
                duration_ms=duration_ms,
                error=str(result.get("error") or "the design program failed"),
                stdout=stdout,
                stats=None,
            )

        stl_path = Path(workspace) / "output.stl"
        if not stl_path.is_file():
            return ProgramExecution(
                status="failed",
                stl=None,
                sha256=None,
                duration_ms=duration_ms,
                error="the design program produced no mesh",
                stdout=stdout,
                stats=None,
            )
        data = stl_path.read_bytes()
        try:
            stats = mesh_stats(data)
        except ValueError as exc:
            return ProgramExecution(
                status="failed",
                stl=None,
                sha256=None,
                duration_ms=duration_ms,
                error=f"the exported mesh is invalid: {exc}",
                stdout=stdout,
                stats=None,
            )

        raw_parts = result.get("parts") or []
        if not isinstance(raw_parts, list) or len(raw_parts) > 80:
            return _failure(duration_ms, stdout, "the manifest lists an invalid part set")
        parts: list[ProgramPartExecution] = []
        names: set[str] = set()
        for item in raw_parts:
            name = item.get("name") if isinstance(item, dict) else None
            if not isinstance(name, str) or name in names:
                return _failure(duration_ms, stdout, "the manifest lists invalid part names")
            names.add(name)
            part_path = Path(workspace) / f"part_{name}.stl"
            if not part_path.is_file():
                return _failure(duration_ms, stdout, f"part {name!r} was not exported")
            part_data = part_path.read_bytes()
            try:
                part_stats = mesh_stats(part_data)
            except ValueError as exc:
                return _failure(
                    duration_ms, stdout, f"part {name!r} mesh is invalid: {exc}"
                )
            parts.append(
                ProgramPartExecution(
                    name=name,
                    stl=part_data,
                    sha256=str(item.get("sha256") or ""),
                    stats=part_stats,
                )
            )
        if not parts:
            return _failure(duration_ms, stdout, "the program exported no parts")

        raw_joints = result.get("joints") or []
        if not isinstance(raw_joints, list) or len(raw_joints) > 6:
            return _failure(duration_ms, stdout, "the manifest lists an invalid joint set")
        joints: list[ProgramJoint] = []
        try:
            for item in raw_joints:
                joint = ProgramJoint.model_validate(item)
                if joint.parent not in names or joint.child not in names:
                    raise ValueError("joint references a part that was not produced")
                if joint.parent == joint.child:
                    raise ValueError("joint must connect two different parts")
                if joint.min_deg > joint.max_deg:
                    raise ValueError("joint limits are inverted")
                joints.append(joint)
        except ValueError as exc:
            return _failure(duration_ms, stdout, f"invalid joint declaration: {exc}")

        return ProgramExecution(
            status="executed",
            stl=data,
            sha256=str(result.get("sha256") or ""),
            duration_ms=duration_ms,
            error=None,
            stdout=stdout,
            stats=stats,
            parts=tuple(parts),
            joints=tuple(joints),
        )


__all__ = [
    "ANGULAR_TOLERANCE_RAD",
    "ProgramPartExecution",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MEMORY_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_SOURCE_LENGTH",
    "ProgramExecution",
    "ProgramRejectedError",
    "SANDBOX_VERSION",
    "TESSELATION_TOLERANCE_MM",
    "run_design_program",
    "static_check",
]
