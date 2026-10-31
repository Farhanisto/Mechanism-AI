import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CadViewer } from "./workspace/CadViewer";

describe("CadViewer camera views", () => {
  it("offers isometric, top, side and front views", () => {
    render(<CadViewer url="/evidence/artifact.stl" />);

    const isometric = screen.getByRole("button", { name: "Isometric" });
    const top = screen.getByRole("button", { name: "Top" });
    expect(screen.getByRole("button", { name: "Side" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Front" })).toBeTruthy();
    expect(isometric.getAttribute("aria-pressed")).toBe("true");
    expect(top.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(top);

    expect(top.getAttribute("aria-pressed")).toBe("true");
    expect(isometric.getAttribute("aria-pressed")).toBe("false");
  });
});
