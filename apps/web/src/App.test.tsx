import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

vi.mock("./landing/LinkageScene", () => ({
  LinkageScene: () => <div data-testid="linkage-scene" />,
}));

describe("App routing", () => {
  afterEach(() => {
    window.location.hash = "";
    cleanup();
  });

  it("renders the marketing landing page at the site root", () => {
    window.location.hash = "";
    render(<App />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/From idea to/i);
  });

  it("renders the engineering workspace at #/app", () => {
    window.location.hash = "#/app";
    render(<App />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(
      /Constraint-driven/i,
    );
  });
});
