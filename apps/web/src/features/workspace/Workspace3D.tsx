import { useState } from "react";

import type { BriefArtifact, CandidateMetrics, SimulationResult } from "../../lib/api";
import { MechanismCanvas } from "../simulation/MechanismCanvas";
import { CadViewer } from "./CadViewer";

type WorkspaceMode = "cad" | "motion" | "concept";

interface Workspace3DProps {
  geometryUrl: string | null;
  geometryArtifactId: string | null;
  simulation: SimulationResult | null;
  brief: BriefArtifact | null;
  metrics: CandidateMetrics | null;
}

const MODES: { id: WorkspaceMode; label: string }[] = [
  { id: "cad", label: "CAD" },
  { id: "motion", label: "Motion" },
  { id: "concept", label: "Concept" },
];

export function Workspace3D({
  geometryUrl,
  geometryArtifactId,
  simulation,
  brief,
  metrics,
}: Workspace3DProps) {
  const [mode, setMode] = useState<WorkspaceMode>(geometryUrl ? "cad" : "motion");

  return (
    <section className="panel workspace">
      <div className="panel-heading">
        <h2>3D workspace</h2>
        <div className="mode-tabs" role="tablist" aria-label="Workspace modes">
          {MODES.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={mode === item.id}
              className={`mode-tab${mode === item.id ? " mode-tab-active" : ""}`}
              onClick={() => setMode(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {mode === "cad" ? (
        <div className="workspace-body">
          <div className="mode-badges">
            <span className="badge badge-verified">verified artifact</span>
            {geometryArtifactId ? <code>{geometryArtifactId}</code> : null}
          </div>
          {geometryUrl ? (
            <CadViewer url={geometryUrl} />
          ) : (
            <p className="empty-state">
              No geometry artifact for this run. Enable the CAD engine (`uv sync --extra cad`) or
              run a candidate that compiles.
            </p>
          )}
        </div>
      ) : null}

      {mode === "motion" ? (
        <div className="workspace-body">
          <div className="mode-badges">
            <span className="badge badge-computed">computed state trace</span>
            <span className="mode-note">Rendered from persisted simulation samples</span>
          </div>
          <MechanismCanvas simulation={simulation} brief={brief} metrics={metrics} />
        </div>
      ) : null}

      {mode === "concept" ? (
        <div className="workspace-body">
          <div className="mode-badges">
            <span className="badge badge-unavailable">not available</span>
          </div>
          <p className="empty-state">
            Concept mode is not implemented. Only verified CAD geometry and motion computed from
            persisted state traces are shown; nothing here is an illustrative or model-generated
            animation.
          </p>
        </div>
      ) : null}
    </section>
  );
}
