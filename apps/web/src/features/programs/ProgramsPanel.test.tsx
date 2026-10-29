import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProgramRecord } from "../../lib/api";
import { ProgramsPanel } from "./ProgramsPanel";

const passed: ProgramRecord = {
  program: {
    program_id: "program_001",
    capability_id: "custom_part",
    language: "python",
    entrypoint: "build",
    source: "import cadquery as cq\n\ndef build():\n    return cq.Workplane('XY').box(60, 40, 6)\n",
    declared_parameters: [{ name: "width", value: 60 }],
    expected_bbox: { width_mm: 60, height_mm: 40, thickness_mm: 6 },
    notes: [],
  },
  attempt_number: 1,
  source_hash: "a".repeat(64),
  geometry_artifact_id: "geometry_program_001.stl",
  artifact_hash: "b".repeat(64),
  execution_status: "executed",
  duration_ms: 850,
  error: null,
  evaluation: {
    program_id: "program_001",
    status: "passed",
    metrics: {
      width_mm: 60,
      height_mm: 40,
      thickness_mm: 6,
      volume_mm3: 14230.4,
      triangle_count: 128,
      deterministic: true,
      mesh_valid: true,
      program_status: "executed",
    },
    failed_checks: [],
    evaluator_version: "0.1.0",
    diagnostic_notes: [],
  },
};

const failed: ProgramRecord = {
  ...passed,
  program: { ...passed.program, program_id: "program_002" },
  attempt_number: 2,
  geometry_artifact_id: null,
  execution_status: "failed",
  error: "ValueError: boom",
  evaluation: {
    ...passed.evaluation!,
    program_id: "program_002",
    status: "failed",
    failed_checks: ["program_executed", "mesh_valid"],
    diagnostic_notes: ["Program execution: ValueError: boom"],
  },
};

describe("ProgramsPanel", () => {
  it("renders nothing without programs", () => {
    const { container } = render(
      <ProgramsPanel runId="run_1" programs={[]} expert={false} />,
    );
    expect(container.textContent).toBe("");
  });

  it("shows attempts, checks and downloads", () => {
    render(<ProgramsPanel runId="run_1" programs={[passed, failed]} expert={false} />);

    expect(screen.getByText("program_001")).toBeTruthy();
    expect(screen.getByText("program_002")).toBeTruthy();
    expect(screen.getByText("passed")).toBeTruthy();
    expect(screen.getByText("failed")).toBeTruthy();
    expect(screen.getByText("program_executed")).toBeTruthy();
    expect(screen.getByText("Download STL")).toBeTruthy();
    expect(screen.getAllByText(/ValueError: boom/).length).toBeGreaterThan(0);
  });

  it("reveals program source only in expert mode", () => {
    const beginner = render(
      <ProgramsPanel runId="run_1" programs={[passed]} expert={false} />,
    );
    expect(beginner.container.textContent).not.toContain("Program source");
    beginner.unmount();

    render(<ProgramsPanel runId="run_1" programs={[passed]} expert />);
    expect(screen.getByText(/Program source/)).toBeTruthy();
  });
});
