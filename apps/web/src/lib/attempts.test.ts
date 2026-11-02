import { describe, expect, it } from "vitest";

import type { RunEvent } from "./api";
import { buildAttempts } from "./attempts";

function event(name: string, data: Record<string, unknown>): RunEvent {
  return { event: name, data };
}

describe("buildAttempts", () => {
  it("tracks a four-bar attempt through generation, geometry, simulation and evaluation", () => {
    const attempts = buildAttempts({
      events: [
        event("candidate_generation_started", { attempt_number: 1 }),
        event("candidate_generated", {
          attempt_number: 1,
          candidate_id: "candidate_001",
          parameters: {
            ground_length: 120,
            crank_length: 40,
            coupler_length: 100,
            rocker_length: 90,
          },
        }),
        event("geometry_validated", {
          candidate_id: "candidate_001",
          artifact_id: "geometry_candidate_001.stl",
          generation_status: "generated",
        }),
        event("simulation_completed", { candidate_id: "candidate_001" }),
        event("evaluation_completed", {
          candidate_id: "candidate_001",
          status: "failed",
          failed_constraints: ["trajectory_tolerance"],
        }),
      ],
    });

    expect(attempts).toHaveLength(1);
    expect(attempts[0]).toMatchObject({
      attemptNumber: 1,
      candidateId: "candidate_001",
      status: "failed",
      artifactId: "geometry_candidate_001.stl",
      hasSimulation: true,
      failedChecks: ["trajectory_tolerance"],
    });
    expect(attempts[0].parameters?.ground_length).toBe(120);
  });

  it("tracks program attempts and their failed checks", () => {
    const attempts = buildAttempts({
      events: [
        event("candidate_generation_started", { attempt_number: 1 }),
        event("candidate_generated", {
          attempt_number: 1,
          candidate_id: "program_001",
          declared_parameters: { span: 900 },
        }),
        event("geometry_validated", {
          candidate_id: "program_001",
          artifact_id: "geometry_program_001.stl",
          generation_status: "generated",
        }),
        event("evaluation_completed", {
          candidate_id: "program_001",
          status: "failed",
          failed_checks: ["envelope_width"],
        }),
      ],
    });

    expect(attempts[0]).toMatchObject({
      status: "failed",
      artifactId: "geometry_program_001.stl",
      failedChecks: ["envelope_width"],
      hasSimulation: false,
    });
  });

  it("shows the current attempt as soon as it starts", () => {
    const attempts = buildAttempts({
      events: [event("candidate_generation_started", { attempt_number: 2 })],
    });

    expect(attempts).toEqual([
      expect.objectContaining({ attemptNumber: 2, status: "modeling", artifactId: null }),
    ]);
  });

  it("falls back to persisted records when the event history is empty", () => {
    const attempts = buildAttempts({
      events: [],
      programs: [
        {
          program: { program_id: "program_001" },
          attempt_number: 1,
          geometry_artifact_id: "geometry_program_001.stl",
          evaluation: {
            status: "failed",
            failed_checks: ["envelope_height"],
          },
        } as never,
      ],
    });

    expect(attempts[0]).toMatchObject({
      attemptNumber: 1,
      artifactId: "geometry_program_001.stl",
      status: "failed",
      failedChecks: ["envelope_height"],
    });
  });
});
