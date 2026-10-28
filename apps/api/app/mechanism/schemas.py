from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MechanismType(StrEnum):
    FOUR_BAR_LINKAGE = "four_bar_linkage"


class Units(StrEnum):
    MM = "mm"


class TargetMotionType(StrEnum):
    NEAR_HORIZONTAL = "near_horizontal"


class TargetMotion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TargetMotionType = TargetMotionType.NEAR_HORIZONTAL
    travel_distance: float = Field(gt=0, le=10_000)
    trajectory_tolerance: float = Field(default=5.0, gt=0, le=100)


class HardConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_footprint: float = Field(gt=0, le=10_000)
    complete_motion_cycle: bool = True
    avoid_collisions: bool = True


class NormalizedBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism_type: MechanismType = MechanismType.FOUR_BAR_LINKAGE
    units: Units = Units.MM
    target_motion: TargetMotion
    constraints: HardConstraints
    assumptions: list[str] = Field(default_factory=list)
    evaluator_config: dict[str, float | int | str | bool] = Field(default_factory=dict)


class FourBarParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ground_length: float = Field(gt=0, le=10_000)
    crank_length: float = Field(gt=0, le=10_000)
    coupler_length: float = Field(gt=0, le=10_000)
    rocker_length: float = Field(gt=0, le=10_000)


class InputMotion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_angle_deg: float = Field(ge=-3600, le=3600)
    end_angle_deg: float = Field(ge=-3600, le=3600)


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    mechanism_type: MechanismType = MechanismType.FOUR_BAR_LINKAGE
    parameters: FourBarParameters
    input_motion: InputMotion
    generated_at: datetime
    attempt_number: int = Field(ge=1, le=10)


class Point2D(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)


class TraceSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_s: float = Field(ge=0, le=1)
    input_angle_deg: float
    ground_pivot_a: Point2D
    ground_pivot_b: Point2D
    crank_pin: Point2D
    rocker_pin: Point2D
    output_point: Point2D


class SimulationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    engine: str
    engine_version: str
    time_basis: str = "normalized_cycle"
    samples: list[TraceSample] = Field(default_factory=list)
    cycle_completed: bool = False
    collision_free: bool = False
    simulation_valid: bool = False
    failure_reason: str | None = None


class CandidateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    travel_distance_mm: float = Field(ge=0)
    footprint_mm: float = Field(ge=0)
    trajectory_error_mm: float = Field(ge=0)
    cycle_completed: bool
    collision_free: bool
    simulation_valid: bool


class EvaluationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class Evaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    status: EvaluationStatus
    metrics: CandidateMetrics
    failed_constraints: list[str] = Field(default_factory=list)
    evaluator_version: str
    diagnostic_notes: list[str] = Field(default_factory=list)


class CandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: Candidate
    evaluation: Evaluation | None = None


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Stage(StrEnum):
    QUEUED = "queued"
    PARSE_REQUIREMENTS = "parse_requirements"
    GENERATE_CANDIDATE = "generate_candidate"
    COMPILE_MODEL = "compile_model"
    SIMULATE = "simulate"
    EVALUATE = "evaluate"
    REPAIR = "repair"
    REPORT = "report"
    COMPLETED = "completed"
    FAILED = "failed"


class DesignRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus
    stage: Stage
    original_prompt: str
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    final_candidate_id: str | None = None
    max_candidates: int = Field(default=3, ge=1, le=3)
    no_pass: bool = False


class DesignRunOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_candidates: int = Field(default=3, ge=1, le=3)


class DesignRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=4000)
    options: DesignRunOptions = Field(default_factory=DesignRunOptions)


class RunEventName(StrEnum):
    RUN_STARTED = "run_started"
    REQUIREMENTS_PARSED = "requirements_parsed"
    CANDIDATE_GENERATED = "candidate_generated"
    SIMULATION_COMPLETED = "simulation_completed"
    EVALUATION_COMPLETED = "evaluation_completed"
    REPAIR_STARTED = "repair_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


TERMINAL_EVENTS: frozenset[RunEventName] = frozenset(
    {RunEventName.RUN_COMPLETED, RunEventName.RUN_FAILED}
)
