import type { CandidateRecord } from "../../lib/api";

interface CandidateHistoryProps {
  candidates: CandidateRecord[];
}

export function CandidateHistory({ candidates }: CandidateHistoryProps) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Candidate history</h2>
        <span className="panel-hint">Every attempt is kept, including failed repairs</span>
      </div>

      {candidates.length === 0 ? (
        <p className="empty-state">
          No candidates have been generated for this run yet.
        </p>
      ) : (
        <div className="candidate-grid">
          {candidates.map(({ candidate, evaluation }) => (
            <article className="candidate-card" key={candidate.candidate_id}>
              <header>
                <strong>{candidate.candidate_id}</strong>
                <span className={`pill pill-${evaluation?.status ?? "pending"}`}>
                  {evaluation?.status ?? "pending"}
                </span>
              </header>
              <dl>
                <div>
                  <dt>Ground</dt>
                  <dd>{candidate.parameters.ground_length} mm</dd>
                </div>
                <div>
                  <dt>Crank</dt>
                  <dd>{candidate.parameters.crank_length} mm</dd>
                </div>
                <div>
                  <dt>Coupler</dt>
                  <dd>{candidate.parameters.coupler_length} mm</dd>
                </div>
                <div>
                  <dt>Rocker</dt>
                  <dd>{candidate.parameters.rocker_length} mm</dd>
                </div>
              </dl>
              <p className="candidate-meta">
                Attempt {candidate.attempt_number} · input {candidate.input_motion.start_angle_deg}°
                to {candidate.input_motion.end_angle_deg}°
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
