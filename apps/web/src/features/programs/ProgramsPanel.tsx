import type { ProgramRecord } from "../../lib/api";
import { artifactUrl } from "../../lib/api";

interface ProgramsPanelProps {
  runId: string | null;
  programs: ProgramRecord[];
  expert: boolean;
}

export function ProgramsPanel({ runId, programs, expert }: ProgramsPanelProps) {
  if (programs.length === 0) {
    return null;
  }
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Design programs</h2>
        <span className="panel-hint">
          Model-authored code, executed in a sandbox and verified by the evaluator
        </span>
      </div>
      <ul className="program-list">
        {programs.map((record) => {
          const status = record.evaluation?.status ?? "pending";
          const programName = `program_${String(record.attempt_number).padStart(3, "0")}.py`;
          return (
            <li key={record.program.program_id} className="program-card">
              <header>
                <strong>{record.program.program_id}</strong>
                <span className={`pill pill-${status}`}>{status}</span>
                <span className="mode-note">
                  attempt {record.attempt_number} · {record.execution_status}
                  {record.duration_ms != null ? ` · ${Math.round(record.duration_ms)} ms` : ""}
                  {record.parts && record.parts.length > 0
                    ? ` · ${record.parts.length} part${record.parts.length === 1 ? "" : "s"}`
                    : ""}
                  {record.joints && record.joints.length > 0
                    ? ` · ${record.joints.length} joint${record.joints.length === 1 ? "" : "s"}`
                    : ""}
                </span>
              </header>
              {record.evaluation ? (
                <dl className="candidate-metrics">
                  <div>
                    <dt>W × H × T</dt>
                    <dd>
                      {record.evaluation.metrics.width_mm.toFixed(1)} ×{" "}
                      {record.evaluation.metrics.height_mm.toFixed(1)} ×{" "}
                      {record.evaluation.metrics.thickness_mm.toFixed(1)} mm
                    </dd>
                  </div>
                  <div>
                    <dt>Volume</dt>
                    <dd>
                      {Math.round(record.evaluation.metrics.volume_mm3).toLocaleString()} mm³
                    </dd>
                  </div>
                  <div>
                    <dt>Triangles</dt>
                    <dd>{record.evaluation.metrics.triangle_count}</dd>
                  </div>
                </dl>
              ) : null}
              {record.evaluation && record.evaluation.failed_checks.length > 0 ? (
                <ul className="chip-list">
                  {record.evaluation.failed_checks.map((check) => (
                    <li key={check} className="chip chip-failed">
                      {check}
                    </li>
                  ))}
                </ul>
              ) : null}
              {record.parts && record.parts.length > 0 ? (
                <ul className="chip-list">
                  {record.parts.map((part) => (
                    <li key={part.name} className="chip">
                      {part.name}
                    </li>
                  ))}
                </ul>
              ) : null}
              {record.joints && record.joints.length > 0 ? (
                <p className="version-note">
                  Joints:{" "}
                  {record.joints
                    .map(
                      (joint) =>
                        `${joint.name} (${joint.parent} ↔ ${joint.child}, ${joint.min_deg}°…${joint.max_deg}°)`,
                    )
                    .join(" · ")}
                </p>
              ) : null}
              {record.error ? <p className="version-note">Error: {record.error}</p> : null}
              {record.evaluation && record.evaluation.diagnostic_notes.length > 0 ? (
                <ul className="failure-list">
                  {record.evaluation.diagnostic_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              ) : null}
              <div className="program-actions">
                {runId && record.geometry_artifact_id ? (
                  <a
                    className="artifact-download"
                    href={artifactUrl(runId, record.geometry_artifact_id)}
                    download={record.geometry_artifact_id}
                  >
                    Download STL
                  </a>
                ) : null}
                {runId ? (
                  <a
                    className="artifact-download"
                    href={artifactUrl(runId, programName)}
                    download={programName}
                  >
                    Download program
                  </a>
                ) : null}
              </div>
              {expert ? (
                <details className="program-source">
                  <summary>Program source (sha256 {record.source_hash.slice(0, 12)}…)</summary>
                  <pre className="artifact-json">{record.program.source}</pre>
                </details>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
