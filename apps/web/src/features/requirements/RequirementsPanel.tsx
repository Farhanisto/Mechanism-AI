import type { BriefArtifact, PartBriefArtifact } from "../../lib/api";

interface RequirementsPanelProps {
  briefArtifact: BriefArtifact | null;
  partBrief: PartBriefArtifact | null;
  expert: boolean;
}

export function RequirementsPanel({
  briefArtifact,
  partBrief,
  expert,
}: RequirementsPanelProps) {
  const assessment = briefArtifact?.brief.capability_assessment ?? null;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Requirements</h2>
        <span className="panel-hint">Parsed brief, assumptions and provenance</span>
      </div>

      {partBrief?.brief ? (
        <div className="brief-summary">
          <p>
            <strong>Part brief · {partBrief.brief.part.description}</strong>
            <span>
              envelope {partBrief.brief.part.max_width_mm.toFixed(0)} ×{" "}
              {partBrief.brief.part.max_height_mm.toFixed(0)} ×{" "}
              {partBrief.brief.part.max_thickness_mm.toFixed(0)} mm
            </span>
          </p>
          {partBrief.brief.assumptions.length > 0 ? (
            <details>
              <summary>Assumptions ({partBrief.brief.assumptions.length})</summary>
              <ul className="assumption-list">
                {partBrief.brief.assumptions.map((assumption) => (
                  <li key={assumption}>{assumption}</li>
                ))}
              </ul>
            </details>
          ) : null}
          {partBrief.brief.unknowns.length > 0 ? (
            <p className="version-note">
              Unknowns using documented defaults: {partBrief.brief.unknowns.join(", ")}
            </p>
          ) : null}
          {expert && partBrief.brief.requirement_sources ? (
            <details>
              <summary>Requirement provenance</summary>
              <ul className="assumption-list">
                {Object.entries(partBrief.brief.requirement_sources).map(
                  ([field, source]) => (
                    <li key={field}>
                      {field}: {String(source).replaceAll("_", " ")}
                    </li>
                  ),
                )}
              </ul>
            </details>
          ) : null}
          <div className="capability-panel">
            <p>
              <strong>Capability: custom_part 0.1.0</strong>
              <span className="pill pill-capability-supported">model-authored</span>
            </p>
          </div>
        </div>
      ) : partBrief && partBrief.supported === false ? (
        <p className="empty-state">
          Not supported as a single static part: {partBrief.reason}
        </p>
      ) : !briefArtifact ? (
        <p className="empty-state">
          Requirements appear here once the brief is parsed.
        </p>
      ) : (
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
          {expert && briefArtifact.brief.requirement_sources ? (
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
      )}

      {assessment ? (
        <div className="capability-panel">
          <p>
            <strong>
              Capability: {assessment.capability_id} {assessment.capability_version}
            </strong>
            <span className={`pill pill-capability-${assessment.status}`}>
              {assessment.status.replace("_", " ")}
            </span>
          </p>
          {assessment.unsupported_requirements.length > 0 ? (
            <ul className="failure-list">
              {assessment.unsupported_requirements.map((item) => (
                <li key={item}>Not evaluated: {item}</li>
              ))}
            </ul>
          ) : null}
          {assessment.unavailable_checks.length > 0 ? (
            <ul className="failure-list">
              {assessment.unavailable_checks.map((item) => (
                <li key={item}>Unresolved required check: {item}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
