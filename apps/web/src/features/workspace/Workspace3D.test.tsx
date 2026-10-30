import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SimulationResult } from "../../lib/api";
import { Workspace3D } from "./Workspace3D";

vi.mock("./CadViewer", () => ({
  CadViewer: ({ url }: { url: string }) => <div data-testid="cad-viewer">{url}</div>,
}));

vi.mock("./Motion3DViewer", () => ({
  Motion3DViewer: () => <div data-testid="motion-3d" />,
}));

const simulation: SimulationResult = {
  candidate_id: "candidate_001",
  engine: "mujoco",
  engine_version: "3.17.0",
  time_basis: "normalized_cycle",
  samples: [
    {
      time_s: 0,
      input_angle_deg: 0,
      ground_pivot_a: { x: 0, y: 0 },
      ground_pivot_b: { x: 95, y: 0 },
      crank_pin: { x: 35, y: 0 },
      rocker_pin: { x: 130, y: 60 },
      output_point: { x: 130, y: 60 },
    },
    {
      time_s: 1,
      input_angle_deg: 360,
      ground_pivot_a: { x: 0, y: 0 },
      ground_pivot_b: { x: 95, y: 0 },
      crank_pin: { x: 35, y: 0 },
      rocker_pin: { x: 130, y: 60 },
      output_point: { x: 130, y: 60 },
    },
  ],
  cycle_completed: true,
  collision_free: true,
  simulation_valid: true,
  failure_reason: null,
};

function renderWorkspace(overrides: Partial<Parameters<typeof Workspace3D>[0]> = {}) {
  return render(
    <Workspace3D
      geometryUrl={null}
      geometryArtifactId={null}
      simulation={null}
      brief={null}
      metrics={null}
      {...overrides}
    />,
  );
}

describe("Workspace3D", () => {
  it("renders the three labelled modes", () => {
    renderWorkspace();

    for (const label of ["CAD", "Motion", "Concept"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("shows an explicit state when no geometry artifact exists", () => {
    renderWorkspace();

    fireEvent.click(screen.getByText("CAD"));

    expect(screen.getByText(/No geometry artifact for this run/)).toBeTruthy();
  });

  it("mounts the viewer with the server artifact url", () => {
    renderWorkspace({
      geometryUrl: "http://localhost:8000/geometry_candidate_001.stl",
      geometryArtifactId: "geometry_candidate_001.stl",
    });

    expect(screen.getByTestId("cad-viewer").textContent).toContain(
      "geometry_candidate_001.stl",
    );
    expect(screen.getByText("verified artifact")).toBeTruthy();
  });

  it("labels motion as computed from persisted state traces", () => {
    renderWorkspace({ simulation });

    expect(screen.getByText("computed state trace")).toBeTruthy();
    expect(screen.getByTestId("motion-3d")).toBeTruthy();
    expect(screen.getByText(/measured sweep/)).toBeTruthy();
  });

  it("switches to the CAD view when the geometry artifact arrives", () => {
    const view = renderWorkspace();
    expect(screen.getByText("computed state trace")).toBeTruthy();

    view.rerender(
      <Workspace3D
        geometryUrl="http://localhost:8000/geometry_program_001.stl"
        geometryArtifactId="geometry_program_001.stl"
        simulation={null}
        brief={null}
        metrics={null}
      />,
    );

    expect(screen.getByTestId("cad-viewer")).toBeTruthy();
  });

  it("keeps the user's chosen mode when new geometry arrives", () => {
    const view = renderWorkspace();

    fireEvent.click(screen.getByText("Motion"));
    view.rerender(
      <Workspace3D
        geometryUrl="http://localhost:8000/geometry_program_001.stl"
        geometryArtifactId="geometry_program_001.stl"
        simulation={null}
        brief={null}
        metrics={null}
      />,
    );

    expect(screen.queryByTestId("cad-viewer")).toBeNull();
    expect(screen.getByText("computed state trace")).toBeTruthy();
  });

  it("marks concept mode as not available instead of faking an animation", () => {
    renderWorkspace();

    fireEvent.click(screen.getByText("Concept"));

    expect(screen.getByText(/Concept mode is not implemented/)).toBeTruthy();
    expect(screen.getByText("not available")).toBeTruthy();
  });
});
