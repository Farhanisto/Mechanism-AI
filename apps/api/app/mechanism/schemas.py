from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

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


class RequirementSource(StrEnum):
    USER_PROVIDED = "user_provided"
    AI_PROPOSED = "ai_proposed"
    DEFAULT_ASSUMPTION = "default_assumption"


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    field: str
    blocking: bool = True


class CapabilitySupport(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    NOT_SUPPORTED = "not_supported"
    ERROR = "error"


class CapabilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    capability_version: str
    status: CapabilitySupport
    unsupported_requirements: list[str] = Field(default_factory=list)
    unavailable_checks: list[str] = Field(default_factory=list)


class NormalizedBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism_type: MechanismType = MechanismType.FOUR_BAR_LINKAGE
    units: Units = Units.MM
    target_motion: TargetMotion
    constraints: HardConstraints
    assumptions: list[str] = Field(default_factory=list)
    evaluator_config: dict[str, float | int | str | bool] = Field(default_factory=dict)
    unknowns: list[str] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    requirement_sources: dict[str, RequirementSource] = Field(default_factory=dict)
    capability_assessment: CapabilityAssessment | None = None


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
    geometry_artifact_id: str | None = None


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


class ReferenceComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_engine: str
    reference_engine_version: str
    sample_count: int
    tolerance_mm: float
    max_deviation_mm: float
    mean_deviation_mm: float
    within_tolerance: bool


class SimulationDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compiler_version: str | None = None
    solver: str | None = None
    timestep_s: float | None = None
    settle_target_mm: float | None = None
    settle_step_limit: int | None = None
    max_settle_steps_used: int | None = None
    max_loop_closure_error_mm: float | None = None
    max_solver_iterations: int | None = None
    contacts_enabled: bool = False
    max_contacts: int = 0
    reference_comparison: ReferenceComparison | None = None


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
    warnings: list[str] = Field(default_factory=list)
    diagnostics: SimulationDiagnostics | None = None


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
    AWAITING_CLARIFICATION = "awaiting_clarification"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    CANCELLED = "cancelled"


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
    pending_clarifications: list[ClarificationQuestion] = Field(default_factory=list)
    clarification_answers: dict[str, str] = Field(default_factory=dict)


class DesignRunOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_candidates: int = Field(default=3, ge=1, le=3)


class UserMode(StrEnum):
    BEGINNER = "beginner"
    EXPERT = "expert"


class PreviewMode(StrEnum):
    CONCEPT = "concept"
    CAD = "cad"
    MOTION = "motion"


class DesignRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=4000)
    user_mode: UserMode = UserMode.BEGINNER
    preview_modes: list[PreviewMode] = Field(default_factory=list)
    units: Units = Units.MM
    options: DesignRunOptions = Field(default_factory=DesignRunOptions)


class ClarificationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str] = Field(min_length=1)


class RunEventName(StrEnum):
    RUN_STARTED = "run_started"
    REQUIREMENTS_READY = "requirements_ready"
    CLARIFICATION_REQUIRED = "clarification_required"
    CANDIDATE_GENERATED = "candidate_generated"
    SIMULATION_COMPLETED = "simulation_completed"
    EVALUATION_COMPLETED = "evaluation_completed"
    REPAIR_STARTED = "repair_started"
    ARTIFACT_READY = "artifact_ready"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


TERMINAL_EVENTS: frozenset[RunEventName] = frozenset(
    {RunEventName.RUN_COMPLETED, RunEventName.RUN_FAILED, RunEventName.RUN_CANCELLED}
)


class PlanComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: str
    kind: str
    parameters: dict[str, float] = Field(default_factory=dict)
    material: str | None = None


class PlanJoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    joint_id: str
    kind: Literal["revolute", "prismatic", "fixed", "free"]
    parent: str
    child: str
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    limits_deg: tuple[float, float] | None = None


class PlanGeometryOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str
    component_id: str | None = None
    parameters: dict[str, float | int | str | bool] = Field(default_factory=dict)


class DesignPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    capability_version: str
    components: list[PlanComponent] = Field(default_factory=list)
    joints: list[PlanJoint] = Field(default_factory=list)
    geometry_operations: list[PlanGeometryOp] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    resource_budget: dict[str, float] = Field(default_factory=dict)


class GeometryArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    format: Literal["step", "stl", "mjcf", "svg"]
    units: Units = Units.MM
    compiler_version: str
    generation_status: Literal["generated", "failed"]
    validation_results: dict[str, bool] = Field(default_factory=dict)
    artifact_hash: str | None = None
    error: str | None = None


class ArtifactManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    sha256: str
    size_bytes: int
    written_at: str


class SimulationEngineInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str | None = None
    time_basis: str = "normalized_cycle"
    output_point: str = "rocker_pin"
    settings: dict[str, Any] | None = None


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: DesignRun
    prompt: str
    requirements: dict[str, Any]
    simulation_engine: SimulationEngineInfo
    limits: dict[str, Any]
    collision_model: str
    evaluator_version: str
    provider_calls: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[CandidateRecord] = Field(default_factory=list)
    final_candidate_id: str | None = None
    no_pass: bool = False
    outcome: str
    limitations: list[str] = Field(default_factory=list)
    manifest: list[ArtifactManifestEntry] = Field(default_factory=list)
