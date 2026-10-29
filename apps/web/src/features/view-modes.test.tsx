import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunStatusPanel } from "../components/RunStatusPanel";
import type { BriefArtifact, DesignRun } from "../lib/api";
import { RequirementsPanel } from "./requirements/RequirementsPanel";

const run: DesignRun = {
  run_id: "run_test",
  status: "completed",
  stage: "completed",
  original_prompt: "Design a four-bar linkage.",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  error_code: null,
  final_candidate_id: "candidate_001",
  max_candidates: 3,
  no_pass: false,
  pending_clarifications: [],
  clarification_answers: {},
};

const brief: BriefArtifact = {
  source: "deterministic_fallback",
  brief: {
    target_motion: { type: "near_horizontal", travel_distance: 100, trajectory_tolerance: 5 },
    constraints: { max_footprint: 200, complete_motion_cycle: true, avoid_collisions: true },
    assumptions: ["Near-horizontal target interpreted as a straight level output path."],
    requirement_sources: { "target_motion.travel_distance": "user_provided" },
    capability_assessment: {
      capability_id: "four_bar_linkage",
      capability_version: "0.1.0",
      status: "supported",
      unsupported_requirements: [],
      unavailable_checks: [],
    },
  },
};

describe("Beginner and Expert views", () => {
  it("hides requirement provenance in beginner mode", () => {
    render(<RequirementsPanel briefArtifact={brief} partBrief={null} expert={false} />);

    expect(screen.queryByText("Requirement provenance")).toBeNull();
    expect(screen.getByText(/Capability:/)).toBeTruthy();
  });

  it("shows requirement provenance in expert mode", () => {
    render(<RequirementsPanel briefArtifact={brief} partBrief={null} expert />);

    expect(screen.getByText("Requirement provenance")).toBeTruthy();
  });

  it("hides the raw event log in beginner mode", () => {
    render(
      <RunStatusPanel
        run={run}
        events={[{ event: "run_started", data: {} }]}
        streamState="ended"
        onCancel={() => undefined}
        expert={false}
      />,
    );

    expect(screen.queryByText("run_started")).toBeNull();
  });

  it("shows the raw event log in expert mode", () => {
    render(
      <RunStatusPanel
        run={run}
        events={[{ event: "run_started", data: {} }]}
        streamState="ended"
        onCancel={() => undefined}
        expert
      />,
    );

    expect(screen.getByText("run_started")).toBeTruthy();
  });
});
