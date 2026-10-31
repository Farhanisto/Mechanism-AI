import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DesignInputForm } from "./DesignInputForm";

describe("DesignInputForm", () => {
  it("fills the prompt from an example chip", () => {
    render(<DesignInputForm onSubmit={vi.fn()} disabled={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Bearing housing" }));

    const textarea = screen.getByLabelText("Motion requirement") as HTMLTextAreaElement;
    expect(textarea.value).toContain("bearing housing");
  });

  it("submits with the keyboard shortcut", () => {
    const onSubmit = vi.fn();
    render(<DesignInputForm onSubmit={onSubmit} disabled={false} />);

    const textarea = screen.getByLabelText("Motion requirement");
    fireEvent.change(textarea, { target: { value: "Design a hinge" } });
    fireEvent.keyDown(textarea, { key: "Enter", metaKey: true });

    expect(onSubmit).toHaveBeenCalledWith("Design a hinge", 3);
  });
});
