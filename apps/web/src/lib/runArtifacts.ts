import type { DesignRun } from "./api";

const PROGRAM_CAPABILITIES = new Set(["custom_part", "assembly", "structural_frame"]);

export interface ArtifactPlan {
  brief: boolean;
  partBrief: boolean;
  programs: boolean;
  simulation: boolean;
}

/**
 * Decide which artifacts are worth requesting. Requesting every artifact on every
 * refresh produced permanent 404s (for example brief.json on program runs) and noisy
 * 404s before an artifact had been written.
 */
export function artifactPlan(run: DesignRun): ArtifactPlan {
  const capability = run.capability_id ?? "";
  const isFourBar = capability === "four_bar_linkage";
  const isProgram = PROGRAM_CAPABILITIES.has(capability);
  const parsing = run.status === "queued" || run.stage === "parse_requirements";
  const terminal = ["completed", "failed", "cancelled"].includes(run.status);
  // Clarification pauses still happen after the brief has been persisted.
  const briefReady = !parsing || terminal || run.status === "awaiting_clarification";

  return {
    brief: isFourBar && briefReady,
    partBrief: isProgram && briefReady,
    programs: isProgram && terminal,
    simulation: isFourBar && Boolean(run.final_candidate_id),
  };
}
