import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunStatusPanel } from "../components/RunStatusPanel";
import type { BriefArtifact, DesignRun, PartBriefArtifact } from "../lib/api";
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

const partBrief: PartBriefArtifact = {
  source: "meta_model",
  brief: {
    part: {
      description: "Simplified helmet outer shell",
      max_width_mm: 280,
      max_height_mm: 300,
      max_thickness_mm: 350,
      notes: [],
    },
    assumptions: ["Shell only."],
    unknowns: [],
    unsupported_requirements: ["visor mechanism", "impact protection and certification"],
    requirement_sources: { "part.max_width_mm": "ai_proposed" },
  },
};

describe("Part requirements", () => {
  it("lists omitted components and analyses as not evaluated", () => {
    render(
      <RequirementsPanel
        briefArtifact={null}
        partBrief={partBrief}
        expert={false}
      />,
    );

    expect(screen.getByText(/Simplified helmet outer shell/)).toBeTruthy();
    expect(screen.getByText(/Not evaluated: visor mechanism/)).toBeTruthy();
    expect(
      screen.getByText(/Not evaluated: impact protection and certification/),
    ).toBeTruthy();
  });

  it("renders the model's rejection reason for unsupported requests", () => {
    render(
      <RequirementsPanel
        briefArtifact={null}
        partBrief={{ source: "meta_model", supported: false, reason: "multi-component product" }}
        expert={false}
      />,
    );

    expect(screen.getByText(/Not supported as a single static part/)).toBeTruthy();
  });
});

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
