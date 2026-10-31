import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LandingPage } from "./LandingPage";

vi.mock("./LinkageScene", () => ({
  LinkageScene: () => <div data-testid="linkage-scene" />,
}));

describe("LandingPage", () => {
  it("presents the brand, hero and primary calls to action", () => {
    render(<LandingPage />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/From idea to/i);
    expect(screen.getByRole("link", { name: "Mechanism AI home" })).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /Start Designing/i })[0].getAttribute("href")).toBe(
      "#/app",
    );
    expect(screen.getAllByRole("link", { name: /Get Early Access/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("linkage-scene").length).toBeGreaterThan(0);
  });

  it("describes the four-step workflow and the platform capabilities", () => {
    render(<LandingPage />);

    for (const step of [
      "Describe Your Idea",
      "Generate Your Design",
      "Simulate the Physics",
      "Validate and Export",
    ]) {
      expect(screen.getByText(step)).toBeTruthy();
    }
    for (const capability of [
      "AI-Powered Design",
      "3D CAD Generation",
      "Physics Simulation",
      "Engineering Validation",
      "Engineering Exports",
    ]) {
      expect(screen.getByText(capability)).toBeTruthy();
    }
  });

  it("distinguishes available industries from planned ones", () => {
    render(<LandingPage />);

    expect(screen.getByText("Initial product focus")).toBeTruthy();
    expect(screen.getAllByText("Mechanical Engineering").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fashion Engineering").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Robotics Design").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Coming soon")).toHaveLength(2);
    expect(screen.getByText("Exploratory")).toBeTruthy();
  });

  it("shows completed and planned roadmap phases honestly", () => {
    render(<LandingPage />);

    for (let phase = 1; phase <= 5; phase += 1) {
      expect(screen.getByText(`Phase ${phase}`)).toBeTruthy();
    }
    expect(screen.getByText("In development")).toBeTruthy();
    expect(screen.getByText(/Planned and in-development phases are not available today/)).toBeTruthy();
  });

  it("opens and closes the mobile navigation", () => {
    render(<LandingPage />);

    const openButton = screen.getByRole("button", { name: "Open menu" });
    fireEvent.click(openButton);

    expect(screen.getByRole("button", { name: "Close menu" })).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Open menu" })).toBeTruthy();
  });
});
