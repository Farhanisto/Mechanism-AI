import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SimulationResult } from "../../lib/api";
import { OutputAnglePlot, outputAngles } from "./OutputAnglePlot";

function sample(angleDeg: number, x: number, y: number) {
  return {
    time_s: 0,
    input_angle_deg: angleDeg,
    ground_pivot_a: { x: 0, y: 0 },
    ground_pivot_b: { x: 95, y: 0 },
    crank_pin: { x: 35, y: 0 },
    rocker_pin: { x, y },
    output_point: { x, y },
  };
}

const simulation: SimulationResult = {
  candidate_id: "candidate_001",
  engine: "mujoco",
  engine_version: "3.17.0",
  time_basis: "normalized_cycle",
  samples: [
    sample(0, 130, 60),
    sample(90, 150, 30),
    sample(180, 140, -20),
    sample(270, 110, 40),
  ],
  cycle_completed: true,
  collision_free: true,
  simulation_valid: true,
  failure_reason: null,
};

describe("OutputAnglePlot", () => {
  it("computes the rocker angle for each sample", () => {
    const angles = outputAngles(simulation);
    expect(angles).toHaveLength(4);
    expect(angles[0]).toBeCloseTo(Math.atan2(60, 35) * (180 / Math.PI), 4);
  });

  it("draws a curve and reports the measured sweep", () => {
    const { container } = render(<OutputAnglePlot simulation={simulation} />);

    expect(container.querySelector("polyline.angle-line")).not.toBeNull();
    expect(container.textContent).toMatch(/measured sweep \d+\.\d°|measured sweep \d°/);
  });
});
