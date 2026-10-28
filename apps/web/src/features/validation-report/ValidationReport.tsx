import type {
  BriefArtifact,
  CandidateRecord,
  DesignRun,
  SimulationResult,
} from "../../lib/api";

interface ValidationReportProps {
  run: DesignRun | null;
  candidates: CandidateRecord[];
  briefArtifact: BriefArtifact | null;
  simulation: SimulationResult | null;
}

export function ValidationReport({
  run,
  candidates,
  briefArtifact,
  simulation,
}: ValidationReportProps) {
  const finalRecord =
    (run?.final_candidate_id
      ? candidates.find(
          (record) => record.candidate.candidate_id === run.final_candidate_id,
        )
      : null) ?? candidates.at(-1);
  const evaluation = finalRecord?.evaluation ?? null;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Validation report</h2>
        <span className="panel-hint">The evaluator owns pass/fail</span>
      </div>

      {run?.error_code ? (
        <div className="notice notice-error">
          <strong>{run.error_code}</strong>
          <span>This run stopped honestly before producing an evaluated candidate.</span>
        </div>
      ) : null}

      {run?.no_pass ? (
        candidates.length === 0 ? (
          <div className="notice notice-error">
            <strong>Request not supported</strong>
            <span>
              No registered capability can handle this request, so nothing was generated or
              evaluated. The capability assessment below names what is missing.
            </span>
          </div>
        ) : (
          <div className="notice notice-warning">
            <strong>No passing candidate</strong>
            <span>
              The best attempt is shown below. Failing the evaluator is a valid outcome; it is
              not reported as a successful design.
            </span>
          </div>
        )
      ) : null}

      {briefArtifact ? (
        <div className="brief-summary">
          <p>
            <strong>
              {briefArtifact.source === "meta_model" ? "Meta model brief" : "Fallback brief"}
            </strong>
            <span>
              {briefArtifact.brief.target_motion.travel_distance.toFixed(0)} mm travel ·{" "}
              {briefArtifact.brief.target_motion.trajectory_tolerance.toFixed(0)} mm
              tolerance · {briefArtifact.brief.constraints.max_footprint.toFixed(0)} mm
              footprint
            </span>
          </p>
          {briefArtifact.brief.assumptions.length > 0 ? (
            <details>
              <summary>
                Assumptions ({briefArtifact.brief.assumptions.length})
              </summary>
              <ul className="assumption-list">
                {briefArtifact.brief.assumptions.map((assumption) => (
                  <li key={assumption}>{assumption}</li>
                ))}
              </ul>
            </details>
          ) : null}
          {briefArtifact.brief.unknowns && briefArtifact.brief.unknowns.length > 0 ? (
            <p className="version-note">
              Unknowns using documented defaults: {briefArtifact.brief.unknowns.join(", ")}
            </p>
          ) : null}
          {briefArtifact.brief.requirement_sources ? (
            <details>
              <summary>Requirement provenance</summary>
              <ul className="assumption-list">
                {Object.entries(briefArtifact.brief.requirement_sources).map(
                  ([field, source]) => (
                    <li key={field}>
                      {field}: {String(source).replaceAll("_", " ")}
                    </li>
                  ),
                )}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}

      {briefArtifact?.brief.capability_assessment ? (
        <div className="capability-panel">
          <p>
            <strong>
              Capability: {briefArtifact.brief.capability_assessment.capability_id}{" "}
              {briefArtifact.brief.capability_assessment.capability_version}
            </strong>
            <span
              className={`pill pill-capability-${briefArtifact.brief.capability_assessment.status}`}
            >
              {briefArtifact.brief.capability_assessment.status.replace("_", " ")}
            </span>
          </p>
          {briefArtifact.brief.capability_assessment.unsupported_requirements.length > 0 ? (
            <ul className="failure-list">
              {briefArtifact.brief.capability_assessment.unsupported_requirements.map(
                (item) => (
                  <li key={item}>Not evaluated: {item}</li>
                ),
              )}
            </ul>
          ) : null}
          {briefArtifact.brief.capability_assessment.unavailable_checks.length > 0 ? (
            <ul className="failure-list">
              {briefArtifact.brief.capability_assessment.unavailable_checks.map((item) => (
                <li key={item}>Unresolved required check: {item}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {evaluation ? (
        <>
          <div className={`status-line status-${evaluation.status}`}>
            <span className="status-dot" />
            <strong>{evaluation.status.toUpperCase()}</strong>
            <span>{evaluation.candidate_id}</span>
          </div>
          <table className="metrics-table">
            <tbody>
              <tr>
                <th>Travel distance</th>
                <td>{evaluation.metrics.travel_distance_mm.toFixed(2)} mm</td>
              </tr>
              <tr>
                <th>Footprint</th>
                <td>{evaluation.metrics.footprint_mm.toFixed(2)} mm</td>
              </tr>
              <tr>
                <th>Trajectory error</th>
                <td>{evaluation.metrics.trajectory_error_mm.toFixed(2)} mm</td>
              </tr>
              <tr>
                <th>Cycle completed</th>
                <td>{evaluation.metrics.cycle_completed ? "yes" : "no"}</td>
              </tr>
              <tr>
                <th>Collision-free</th>
                <td>{evaluation.metrics.collision_free ? "yes" : "no"}</td>
              </tr>
              <tr>
                <th>Simulation valid</th>
                <td>{evaluation.metrics.simulation_valid ? "yes" : "no"}</td>
              </tr>
            </tbody>
          </table>
          {evaluation.failed_constraints.length > 0 ? (
            <ul className="failure-list">
              {evaluation.diagnostic_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
          <p className="version-note">Evaluator {evaluation.evaluator_version}</p>
          {simulation ? (
            <details className="sim-settings">
              <summary>
                Simulation settings · {simulation.engine} {simulation.engine_version}
              </summary>
              <ul>
                <li>Time basis: {simulation.time_basis}</li>
                {simulation.diagnostics?.compiler_version ? (
                  <li>MJCF compiler: {simulation.diagnostics.compiler_version}</li>
                ) : null}
                {simulation.diagnostics?.solver ? (
                  <li>
                    Solver: {simulation.diagnostics.solver}
                    {simulation.diagnostics.timestep_s != null
                      ? ` · timestep ${simulation.diagnostics.timestep_s} s`
                      : ""}
                  </li>
                ) : null}
                {simulation.diagnostics?.max_loop_closure_error_mm != null ? (
                  <li>
                    Max loop-closure error:{" "}
                    {simulation.diagnostics.max_loop_closure_error_mm.toExponential(2)} mm
                  </li>
                ) : null}
                {simulation.diagnostics?.reference_comparison ? (
                  <li>
                    Reference comparison: max deviation{" "}
                    {simulation.diagnostics.reference_comparison.max_deviation_mm.toExponential(
                      2,
                    )}{" "}
                    mm (tolerance {simulation.diagnostics.reference_comparison.tolerance_mm} mm,{" "}
                    {simulation.diagnostics.reference_comparison.within_tolerance
                      ? "within tolerance"
                      : "OUTSIDE tolerance"}
                    )
                  </li>
                ) : null}
                <li>
                  Contacts: {simulation.diagnostics?.contacts_enabled ? "enabled" : "disabled"} ·
                  samples {simulation.samples.length}
                </li>
              </ul>
            </details>
          ) : null}
        </>
      ) : (
        <p className="empty-state">
          No evaluation yet. Results will show the measured metrics, failed constraints and
          evaluator version for each candidate.
        </p>
      )}
    </section>
  );
}
