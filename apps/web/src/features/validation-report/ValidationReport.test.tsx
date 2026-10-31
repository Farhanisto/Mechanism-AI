import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProgramRecord } from "../../lib/api";
import { ValidationReport } from "./ValidationReport";

const passedProgram: ProgramRecord = {
  program: {
    program_id: "program_001",
    capability_id: "custom_part",
    language: "python",
    entrypoint: "build",
    source: "def build(): ...",
    declared_parameters: [],
    expected_bbox: { width_mm: 70, height_mm: 60, thickness_mm: 60 },
    notes: [],
  },
  attempt_number: 1,
  source_hash: "hash",
  geometry_artifact_id: "geometry_program_001.stl",
  artifact_hash: "hash",
  execution_status: "executed",
  duration_ms: 1200,
  error: null,
  parts: [],
  joints: [],
  evaluation: {
    program_id: "program_001",
    status: "passed",
    metrics: {
      width_mm: 70,
      height_mm: 60,
      thickness_mm: 60,
      volume_mm3: 159_830,
      triangle_count: 3654,
      deterministic: true,
      mesh_valid: true,
      program_status: "executed",
      part_count: 1,
      joint_count: 0,
    },
    failed_checks: [],
    evaluator_version: "0.2.0",
    diagnostic_notes: [],
  },
};

describe("ValidationReport", () => {
  it("reports a model-authored program evaluation instead of claiming no result", () => {
    render(
      <ValidationReport
        run={null}
        candidates={[]}
        programs={[passedProgram]}
        simulation={null}
        expert={false}
      />,
    );

    expect(screen.getByText("PASSED")).toBeTruthy();
    expect(screen.getByText("program_001")).toBeTruthy();
    expect(screen.getByText("Measured envelope")).toBeTruthy();
    expect(screen.getByText(/70\.0 × 60\.0 × 60\.0 mm/)).toBeTruthy();
    expect(screen.getByText("Evaluator 0.2.0")).toBeTruthy();
  });
});
