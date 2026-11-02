import { useState, type FormEvent, type KeyboardEvent } from "react";

const EXAMPLE_PROMPT =
  "Design a compact four-bar linkage that produces approximately 100 mm of " +
  "near-horizontal movement, fits within a 200 mm footprint, completes its motion " +
  "cycle, and avoids collisions.";

const EXAMPLES = [
  { label: "Four-bar linkage", prompt: EXAMPLE_PROMPT },
  {
    label: "Bearing housing",
    prompt:
      "Design a bearing housing with a 70 × 60 × 40 mm base. Add a central cylindrical " +
      "bearing seat with a 30 mm bore, four mounting holes, and two reinforcing ribs. " +
      "Include 3 mm fillets on the external edges.",
  },
  {
    label: "Lever arm",
    prompt:
      "Design a lever arm with rounded ends, a 12 mm pivot through-hole, a 50 mm " +
      "elongated slot, and a recessed mounting surface.",
  },
  {
    label: "Suspension bridge",
    prompt:
      "Design a small suspension bridge with an overall length of 30,000 mm, a deck width " +
      "of 4,000 mm, two main support towers 6,000 mm high, two main suspension cables, " +
      "hangers spaced every 1,500 mm, anchor blocks at both ends and guardrails on both " +
      "sides. Generate a complete 3D CAD assembly.",
  },
];

interface DesignInputFormProps {
  onSubmit: (prompt: string, maxCandidates: number) => void;
  disabled: boolean;
}

export function DesignInputForm({ onSubmit, disabled }: DesignInputFormProps) {
  const [prompt, setPrompt] = useState("");
  const [maxCandidates, setMaxCandidates] = useState(3);

  const submitPrompt = () => {
    const trimmed = prompt.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSubmit(trimmed, maxCandidates);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitPrompt();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submitPrompt();
    }
  };

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Design brief</h2>
        <span className="panel-hint">Natural language in, testable requirements out</span>
      </div>
      <form onSubmit={handleSubmit}>
        <label htmlFor="prompt">Motion requirement</label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder={EXAMPLE_PROMPT}
          rows={6}
          maxLength={4000}
          disabled={disabled}
          onKeyDown={handleKeyDown}
        />
        <div className="example-chips" role="group" aria-label="Example design briefs">
          <span className="example-label">Try an example</span>
          {EXAMPLES.map((example) => (
            <button
              type="button"
              key={example.label}
              className="example-chip"
              onClick={() => setPrompt(example.prompt)}
              disabled={disabled}
            >
              {example.label}
            </button>
          ))}
        </div>
        <div className="form-row">
          <div className="form-field">
            <label htmlFor="max-candidates">Candidate budget</label>
            <select
              id="max-candidates"
              value={maxCandidates}
              onChange={(event) => setMaxCandidates(Number(event.target.value))}
              disabled={disabled}
            >
              <option value={1}>1 candidate</option>
              <option value={2}>2 candidates</option>
              <option value={3}>3 candidates</option>
            </select>
          </div>
          <button type="submit" disabled={disabled || !prompt.trim()}>
            {disabled ? "Starting run..." : "Start design run"}
          </button>
        </div>
        <div className="form-meta">
          <span className="panel-hint">⌘ / Ctrl + Enter to start</span>
          <span className="panel-hint">{prompt.length} / 4000</span>
        </div>
        <p className="panel-hint form-expectation">
          Each candidate adds one model call; runs usually take 10–30 s. Clarification
          questions pause the run until answered.
        </p>
      </form>
    </section>
  );
}
