import { useState, type FormEvent } from "react";

const EXAMPLE_PROMPT =
  "Design a compact four-bar linkage that produces approximately 100 mm of " +
  "near-horizontal movement, fits within a 200 mm footprint, completes its motion " +
  "cycle, and avoids collisions.";

interface DesignInputFormProps {
  onSubmit: (prompt: string, maxCandidates: number) => void;
  disabled: boolean;
}

export function DesignInputForm({ onSubmit, disabled }: DesignInputFormProps) {
  const [prompt, setPrompt] = useState(EXAMPLE_PROMPT);
  const [maxCandidates, setMaxCandidates] = useState(3);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed) {
      return;
    }
    onSubmit(trimmed, maxCandidates);
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
          rows={6}
          maxLength={4000}
          disabled={disabled}
        />
        <div className="form-row">
          <div>
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
      </form>
    </section>
  );
}
