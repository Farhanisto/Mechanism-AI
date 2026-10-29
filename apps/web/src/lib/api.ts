export type RunStatus =
  | "queued"
  | "running"
  | "awaiting_clarification"
  | "completed"
  | "failed"
  | "cancelled";

export type RunStage =
  | "queued"
  | "parse_requirements"
  | "generate_candidate"
  | "compile_model"
  | "simulate"
  | "evaluate"
  | "repair"
  | "report"
  | "completed"
  | "failed"
  | "cancelled";

export interface ClarificationQuestion {
  question_id: string;
  question: string;
  field: string;
  blocking: boolean;
}

export interface DesignRun {
  run_id: string;
  status: RunStatus;
  stage: RunStage;
  original_prompt: string;
  created_at: string;
  updated_at: string;
  error_code: string | null;
  final_candidate_id: string | null;
  max_candidates: number;
  no_pass: boolean;
  pending_clarifications: ClarificationQuestion[];
  clarification_answers: Record<string, string>;
}

export interface RunEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface FourBarParameters {
  ground_length: number;
  crank_length: number;
  coupler_length: number;
  rocker_length: number;
}

export interface InputMotion {
  start_angle_deg: number;
  end_angle_deg: number;
}

export interface Candidate {
  candidate_id: string;
  mechanism_type: string;
  parameters: FourBarParameters;
  input_motion: InputMotion;
  generated_at: string;
  attempt_number: number;
  geometry_artifact_id?: string | null;
}

export interface CandidateMetrics {
  travel_distance_mm: number;
  footprint_mm: number;
  trajectory_error_mm: number;
  cycle_completed: boolean;
  collision_free: boolean;
  simulation_valid: boolean;
}

export interface Evaluation {
  candidate_id: string;
  status: "passed" | "failed" | "error";
  metrics: CandidateMetrics;
  failed_constraints: string[];
  evaluator_version: string;
  diagnostic_notes: string[];
}

export interface CandidateRecord {
  candidate: Candidate;
  evaluation: Evaluation | null;
}

export interface Point2D {
  x: number;
  y: number;
}

export interface TraceSample {
  time_s: number;
  input_angle_deg: number;
  ground_pivot_a: Point2D;
  ground_pivot_b: Point2D;
  crank_pin: Point2D;
  rocker_pin: Point2D;
  output_point: Point2D;
}

export interface ReferenceComparison {
  reference_engine: string;
  reference_engine_version: string;
  sample_count: number;
  tolerance_mm: number;
  max_deviation_mm: number;
  mean_deviation_mm: number;
  within_tolerance: boolean;
}

export interface SimulationDiagnostics {
  compiler_version?: string | null;
  solver?: string | null;
  timestep_s?: number | null;
  settle_target_mm?: number | null;
  settle_step_limit?: number | null;
  max_settle_steps_used?: number | null;
  max_loop_closure_error_mm?: number | null;
  max_solver_iterations?: number | null;
  contacts_enabled?: boolean;
  max_contacts?: number;
  reference_comparison?: ReferenceComparison | null;
}

export interface SimulationResult {
  candidate_id: string;
  engine: string;
  engine_version: string;
  time_basis: string;
  samples: TraceSample[];
  cycle_completed: boolean;
  collision_free: boolean;
  simulation_valid: boolean;
  failure_reason: string | null;
  diagnostics?: SimulationDiagnostics | null;
}

export interface BriefArtifact {
  source: "meta_model" | "deterministic_fallback";
  brief: {
    target_motion: {
      type: string;
      travel_distance: number;
      trajectory_tolerance: number;
    };
    constraints: {
      max_footprint: number;
      complete_motion_cycle: boolean;
      avoid_collisions: boolean;
    };
    assumptions: string[];
    unknowns?: string[];
    requirement_sources?: Record<string, string>;
    clarification_questions?: ClarificationQuestion[];
    capability_assessment?: {
      capability_id: string;
      capability_version: string;
      status: "supported" | "partial" | "not_supported" | "error";
      unsupported_requirements: string[];
      unavailable_checks: string[];
    } | null;
  };
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

const TERMINAL_EVENTS = new Set(["run_completed", "run_failed", "run_cancelled"]);
const EVENT_NAMES = [
  "run_started",
  "requirements_ready",
  "clarification_required",
  "capability_selected",
  "candidate_generated",
  "geometry_validated",
  "simulation_completed",
  "evaluation_completed",
  "repair_started",
  "artifact_ready",
  "run_completed",
  "run_failed",
  "run_cancelled",
];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Request failed (${response.status}): ${detail}`);
  }

  return (await response.json()) as T;
}

export function createDesignRun(prompt: string, maxCandidates: number): Promise<DesignRun> {
  return request<DesignRun>("/design-runs", {
    method: "POST",
    body: JSON.stringify({ prompt, options: { max_candidates: maxCandidates } }),
  });
}

export function getDesignRun(runId: string): Promise<DesignRun> {
  return request<DesignRun>(`/design-runs/${runId}`);
}

export function listCandidates(runId: string): Promise<CandidateRecord[]> {
  return request<CandidateRecord[]>(`/design-runs/${runId}/candidates`);
}

export function cancelDesignRun(runId: string): Promise<DesignRun> {
  return request<DesignRun>(`/design-runs/${runId}/cancel`, { method: "POST" });
}

export function submitClarifications(
  runId: string,
  answers: Record<string, string>,
): Promise<DesignRun> {
  return request<DesignRun>(`/design-runs/${runId}/clarifications`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}

export function getArtifact<T>(runId: string, name: string): Promise<T> {
  return request<T>(`/design-runs/${runId}/artifacts/${encodeURIComponent(name)}`);
}

export function artifactUrl(runId: string, name: string): string {
  return `${API_BASE}/design-runs/${runId}/artifacts/${encodeURIComponent(name)}`;
}

export type StreamStatus = "live" | "reconnecting";

interface SubscriptionHandlers {
  onEvent: (event: RunEvent) => void;
  onTerminal: () => void;
  onStatusChange: (status: StreamStatus) => void;
}

export function subscribeToRun(runId: string, handlers: SubscriptionHandlers): () => void {
  const source = new EventSource(`${API_BASE}/design-runs/${runId}/events`);
  let finished = false;

  const handleEvent = (message: MessageEvent<string>) => {
    const event: RunEvent = {
      event: message.type,
      data: JSON.parse(message.data) as Record<string, unknown>,
    };
    handlers.onEvent(event);

    if (TERMINAL_EVENTS.has(event.event) && !finished) {
      finished = true;
      source.close();
      handlers.onTerminal();
    }
  };

  for (const name of EVENT_NAMES) {
    source.addEventListener(name, handleEvent as EventListener);
  }

  source.onopen = () => {
    handlers.onStatusChange("live");
  };

  source.onerror = () => {
    if (finished) {
      return;
    }
    // Keep the EventSource open: the browser retries automatically and the
    // server replays the full event history on every (re)connect.
    handlers.onStatusChange("reconnecting");
  };

  return () => {
    finished = true;
    source.close();
  };
}
