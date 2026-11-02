import type { CandidateRecord, ProgramRecord, RunEvent } from "./api";

export type AttemptStatus =
  | "queued"
  | "modeling"
  | "compiling"
  | "simulating"
  | "evaluating"
  | "passed"
  | "failed";

export interface AttemptView {
  attemptNumber: number;
  candidateId: string | null;
  status: AttemptStatus;
  artifactId: string | null;
  failedChecks: string[];
  parameters: Record<string, number> | null;
  hasSimulation: boolean;
}

interface AttemptSources {
  events: RunEvent[];
  programs?: ProgramRecord[];
  candidates?: CandidateRecord[];
}

function numberRecord(value: unknown): Record<string, number> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const entries = Object.entries(value as Record<string, unknown>).filter(
    (entry): entry is [string, number] => typeof entry[1] === "number",
  );
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

function attemptNumberFrom(data: Record<string, unknown>): number | null {
  return typeof data.attempt_number === "number" ? data.attempt_number : null;
}

function ensure(map: Map<number, AttemptView>, attemptNumber: number): AttemptView {
  let attempt = map.get(attemptNumber);
  if (!attempt) {
    attempt = {
      attemptNumber,
      candidateId: null,
      status: "queued",
      artifactId: null,
      failedChecks: [],
      parameters: null,
      hasSimulation: false,
    };
    map.set(attemptNumber, attempt);
  }
  return attempt;
}

function findByCandidate(map: Map<number, AttemptView>, candidateId: string | null): AttemptView | null {
  if (!candidateId) {
    return null;
  }
  return (
    [...map.values()].find((attempt) => attempt.candidateId === candidateId) ?? null
  );
}

/**
 * Turn the live event stream (and, when events are unavailable after a restart,
 * the persisted candidate/program records) into a timeline of design attempts.
 */
export function buildAttempts({ events, programs = [], candidates = [] }: AttemptSources): AttemptView[] {
  const map = new Map<number, AttemptView>();

  for (const event of events) {
    const data = event.data;
    const attemptNumber = attemptNumberFrom(data);
    const candidateId = typeof data.candidate_id === "string" ? data.candidate_id : null;

    if (event.event === "candidate_generation_started" && attemptNumber !== null) {
      const attempt = ensure(map, attemptNumber);
      attempt.status = "modeling";
      continue;
    }

    if (event.event === "candidate_generated" && attemptNumber !== null) {
      const attempt = ensure(map, attemptNumber);
      attempt.status = "compiling";
      attempt.candidateId = candidateId;
      attempt.parameters =
        numberRecord(data.parameters) ?? numberRecord(data.declared_parameters);
      continue;
    }

    if (event.event === "geometry_validated") {
      const attempt = findByCandidate(map, candidateId);
      if (attempt) {
        attempt.status = "simulating";
        if (data.generation_status === "generated" && typeof data.artifact_id === "string") {
          attempt.artifactId = data.artifact_id;
        }
      }
      continue;
    }

    if (event.event === "simulation_completed") {
      const attempt = findByCandidate(map, candidateId);
      if (attempt) {
        attempt.status = "evaluating";
        attempt.hasSimulation = true;
      }
      continue;
    }

    if (event.event === "evaluation_completed") {
      const attempt = findByCandidate(map, candidateId);
      if (attempt) {
        attempt.status = data.status === "passed" ? "passed" : "failed";
        const failed = data.failed_checks ?? data.failed_constraints;
        attempt.failedChecks = Array.isArray(failed)
          ? failed.filter((item): item is string => typeof item === "string")
          : [];
      }
    }
  }

  // Records cover reconnects/restarts where the in-memory event history is gone.
  for (const record of programs) {
    const attempt = ensure(map, record.attempt_number);
    attempt.candidateId = attempt.candidateId ?? record.program.program_id;
    if (!attempt.artifactId && record.geometry_artifact_id) {
      attempt.artifactId = record.geometry_artifact_id;
    }
    if (record.evaluation) {
      if (attempt.status === "queued") {
        attempt.status = record.evaluation.status === "passed" ? "passed" : "failed";
      }
      attempt.failedChecks =
        attempt.failedChecks.length > 0
          ? attempt.failedChecks
          : record.evaluation.failed_checks;
    }
  }

  for (const record of candidates) {
    const attempt = ensure(map, record.candidate.attempt_number);
    attempt.candidateId = attempt.candidateId ?? record.candidate.candidate_id;
    if (!attempt.artifactId && record.candidate.geometry_artifact_id) {
      attempt.artifactId = record.candidate.geometry_artifact_id;
    }
    if (attempt.parameters === null) {
      attempt.parameters = {
        ground_length: record.candidate.parameters.ground_length,
        crank_length: record.candidate.parameters.crank_length,
        coupler_length: record.candidate.parameters.coupler_length,
        rocker_length: record.candidate.parameters.rocker_length,
      };
    }
    if (record.evaluation) {
      if (attempt.status === "queued") {
        attempt.status = record.evaluation.status === "passed" ? "passed" : "failed";
      }
      attempt.failedChecks =
        attempt.failedChecks.length > 0
          ? attempt.failedChecks
          : record.evaluation.failed_constraints;
    }
  }

  return [...map.values()].sort((a, b) => a.attemptNumber - b.attemptNumber);
}

export function isAttemptInProgress(attempt: AttemptView): boolean {
  return (
    attempt.status === "queued" ||
    attempt.status === "modeling" ||
    attempt.status === "compiling" ||
    attempt.status === "simulating" ||
    attempt.status === "evaluating"
  );
}
