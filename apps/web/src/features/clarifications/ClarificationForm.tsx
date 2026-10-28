import { useState } from "react";

import type { DesignRun } from "../../lib/api";

interface ClarificationFormProps {
  run: DesignRun;
  onSubmit: (answers: Record<string, string>) => void;
}

export function ClarificationForm({ run, onSubmit }: ClarificationFormProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});

  if (run.status !== "awaiting_clarification" || run.pending_clarifications.length === 0) {
    return null;
  }

  const allAnswered = run.pending_clarifications.every(
    (question) => (answers[question.question_id] ?? "").trim().length > 0,
  );

  return (
    <section className="panel clarification-panel">
      <div className="panel-heading">
        <h2>Clarifications needed</h2>
        <span className="panel-hint">
          The run is paused; candidates are only generated after these questions are answered
        </span>
      </div>
      <ul className="clarification-list">
        {run.pending_clarifications.map((question) => (
          <li key={question.question_id}>
            <label htmlFor={`answer-${question.question_id}`}>
              {question.question}
              <span className="clarification-field">{question.field}</span>
            </label>
            <input
              id={`answer-${question.question_id}`}
              type="text"
              value={answers[question.question_id] ?? ""}
              placeholder="Your answer"
              onChange={(event) =>
                setAnswers((current) => ({
                  ...current,
                  [question.question_id]: event.target.value,
                }))
              }
            />
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="clarification-submit"
        disabled={!allAnswered}
        onClick={() => onSubmit(answers)}
      >
        Submit answers and continue
      </button>
    </section>
  );
}
