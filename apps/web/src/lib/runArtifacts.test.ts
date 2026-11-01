import { describe, expect, it } from "vitest";

import type { DesignRun } from "./api";
import { artifactPlan } from "./runArtifacts";

function makeRun(overrides: Partial<DesignRun> = {}): DesignRun {
  return {
    run_id: "run_test",
    status: "running",
    stage: "generate_candidate",
    original_prompt: "test",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    error_code: null,
    final_candidate_id: null,
    max_candidates: 3,
    no_pass: false,
    capability_id: "four_bar_linkage",
    pending_clarifications: [],
    clarification_answers: {},
    ...overrides,
  };
}

describe("artifactPlan", () => {
  it("requests the four-bar brief but not program artifacts", () => {
    const plan = artifactPlan(makeRun());
    expect(plan).toEqual({ brief: true, partBrief: false, programs: false, simulation: false });
  });

  it("waits for parsing before requesting the brief", () => {
    const plan = artifactPlan(makeRun({ stage: "parse_requirements" }));
    expect(plan.brief).toBe(false);
  });

  it("requests the simulation once a final candidate exists", () => {
    const plan = artifactPlan(
      makeRun({ status: "completed", stage: "completed", final_candidate_id: "candidate_001" }),
    );
    expect(plan.brief).toBe(true);
    expect(plan.simulation).toBe(true);
  });

  it("requests part brief and programs for program runs", () => {
    const running = artifactPlan(makeRun({ capability_id: "custom_part" }));
    expect(running).toEqual({
      brief: false,
      partBrief: true,
      programs: false,
      simulation: false,
    });

    const completed = artifactPlan(
      makeRun({ capability_id: "custom_part", status: "completed", stage: "completed" }),
    );
    expect(completed.partBrief).toBe(true);
    expect(completed.programs).toBe(true);
  });

  it("requests the brief during a clarification pause", () => {
    const fourBar = artifactPlan(
      makeRun({ status: "awaiting_clarification", stage: "parse_requirements" }),
    );
    expect(fourBar.brief).toBe(true);

    const program = artifactPlan(
      makeRun({
        capability_id: "custom_part",
        status: "awaiting_clarification",
        stage: "parse_requirements",
      }),
    );
    expect(program.partBrief).toBe(true);
  });

  it("does not request artifacts before routing or while parsing", () => {
    const unrouted = artifactPlan(makeRun({ capability_id: null }));
    expect(unrouted).toEqual({
      brief: false,
      partBrief: false,
      programs: false,
      simulation: false,
    });

    const parsing = artifactPlan(
      makeRun({ capability_id: "custom_part", stage: "parse_requirements" }),
    );
    expect(parsing.partBrief).toBe(false);
  });
});
