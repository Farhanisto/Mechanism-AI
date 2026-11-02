import { useEffect, useState } from "react";

import type { BriefArtifact, CandidateMetrics, SimulationResult } from "../../lib/api";
import { isAttemptInProgress, type AttemptView } from "../../lib/attempts";
import { MechanismCanvas } from "../simulation/MechanismCanvas";
import { CadViewer } from "./CadViewer";
import { Motion3DViewer } from "./Motion3DViewer";
import { OutputAnglePlot } from "./OutputAnglePlot";

type WorkspaceMode = "cad" | "motion" | "concept";

interface Workspace3DProps {
  geometryUrl: string | null;
  geometryArtifactId: string | null;
  verified: boolean;
  attemptCount: number;
  simulation: SimulationResult | null;
  brief: BriefArtifact | null;
  metrics: CandidateMetrics | null;
  attempts?: AttemptView[];
  activeAttemptNumber?: number | null;
  onSelectAttempt?: (attemptNumber: number) => void;
  followLatest?: boolean;
  onFollowLatest?: () => void;
  liveLabel?: string | null;
  isRunning?: boolean;
}

const MODES: { id: WorkspaceMode; label: string }[] = [
  { id: "cad", label: "CAD" },
  { id: "motion", label: "Motion" },
  { id: "concept", label: "Concept" },
];

export function Workspace3D({
  geometryUrl,
  geometryArtifactId,
  verified,
  attemptCount,
  simulation,
  brief,
  metrics,
  attempts = [],
  activeAttemptNumber = null,
  onSelectAttempt,
  followLatest = true,
  onFollowLatest,
  liveLabel = null,
  isRunning = false,
}: Workspace3DProps) {
  const [mode, setMode] = useState<WorkspaceMode>("cad");
  const activeAttempt =
    attempts.find((attempt) => attempt.attemptNumber === activeAttemptNumber) ?? null;
  const badgeClassName =
    isRunning && !activeAttempt
      ? "badge-computed"
      : activeAttempt
        ? activeAttempt.status === "passed"
          ? "badge-verified"
          : activeAttempt.status === "failed"
            ? "badge-failed"
            : "badge-computed"
        : verified
          ? "badge-verified"
          : "badge-unavailable";
  const badgeLabel =
    isRunning && !activeAttempt
      ? "generating"
      : activeAttempt
        ? activeAttempt.status === "passed"
          ? `verified · attempt ${activeAttempt.attemptNumber}`
          : activeAttempt.status === "failed"
            ? `attempt ${activeAttempt.attemptNumber} · failed`
            : `attempt ${activeAttempt.attemptNumber} · ${activeAttempt.status}`
        : verified
          ? "verified artifact"
          : "best attempt (not verified)";
  const [userSelectedMode, setUserSelectedMode] = useState(false);

  useEffect(() => {
    // Open on the most informative verified view as soon as the run produces it,
    // unless the viewer explicitly chose another mode. Without this the workspace
    // stayed on the initial mode because its state was computed before the run.
    if (userSelectedMode) {
      return;
    }
    if (!isRunning && simulation && simulation.samples.length > 0) {
      setMode("motion");
    } else if (isRunning || geometryUrl) {
      setMode("cad");
    }
  }, [geometryUrl, simulation, userSelectedMode, isRunning]);

  const selectMode = (next: WorkspaceMode) => {
    setUserSelectedMode(true);
    setMode(next);
  };

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
              onClick={() => selectMode(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {attempts.length > 0 || (isRunning && liveLabel) ? (
        <div className="attempt-bar" role="group" aria-label="Design attempts">
          <span className="attempt-bar-label">Attempts</span>
          {attempts.map((attempt) => {
            const active = attempt.attemptNumber === activeAttemptNumber;
            return (
              <button
                key={attempt.attemptNumber}
                type="button"
                className={`attempt-chip attempt-${attempt.status}${
                  active ? " is-active" : ""
                }`}
                aria-pressed={active}
                title={
                  attempt.failedChecks.length > 0
                    ? `Failed checks: ${attempt.failedChecks.join(", ")}`
                    : `Attempt ${attempt.attemptNumber}: ${attempt.status}`
                }
                onClick={() => onSelectAttempt?.(attempt.attemptNumber)}
              >
                <span className={`attempt-dot attempt-dot-${attempt.status}`} />
                Attempt {attempt.attemptNumber}
                {isAttemptInProgress(attempt) ? (
                  <span className="attempt-spinner" aria-hidden="true" />
                ) : null}
              </button>
            );
          })}
          {!followLatest && attempts.length > 0 && onFollowLatest ? (
            <button type="button" className="attempt-follow" onClick={onFollowLatest}>
              <span className="attempt-dot attempt-dot-live" />
              Live
            </button>
          ) : null}
          {isRunning && liveLabel ? (
            <span className="attempt-live" role="status">
              <span className="attempt-spinner" aria-hidden="true" />
              {liveLabel}
            </span>
          ) : null}
        </div>
      ) : null}

      {mode === "cad" ? (
        <div className="workspace-body">
          <div className="mode-badges">
            {activeAttempt || geometryUrl || isRunning ? (
              <span className={`badge ${badgeClassName}`}>{badgeLabel}</span>
            ) : null}
            {geometryArtifactId ? <code>{geometryArtifactId}</code> : null}
          </div>
          {geometryUrl ? (
            <CadViewer url={geometryUrl} />
          ) : isRunning ? (
            <div className="workspace-loading" role="status">
              <span className="attempt-spinner" aria-hidden="true" />
              <p>{liveLabel ?? "Generating geometry…"}</p>
            </div>
          ) : (
            <p className="empty-state">
              {attemptCount > 0
                ? "No candidate produced a geometry artifact. Check the Programs panel for the "
                  + "attempt errors."
                : "No geometry artifact was produced for this run because no candidate was "
                  + "generated or compiled."}
            </p>
          )}
        </div>
      ) : null}

      {mode === "motion" ? (
        <div className="workspace-body">
          <div className="mode-badges">
            <span className="badge badge-computed">computed state trace</span>
            <span className="mode-note">
              3D animation built from persisted simulation samples
            </span>
          </div>
          {simulation && simulation.samples.length > 0 ? (
            <>
              <Motion3DViewer simulation={simulation} />
              <OutputAnglePlot simulation={simulation} />
              <details className="motion-trace">
                <summary>Computed path trace (2D)</summary>
                <MechanismCanvas simulation={simulation} brief={brief} metrics={metrics} />
              </details>
            </>
          ) : (
            <p className="empty-state">
              No computed motion trace for this run. The four-bar path produces motion
              samples; assembly runs verify static articulation only.
            </p>
          )}
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
