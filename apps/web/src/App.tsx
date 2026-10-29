import { useState } from "react";

import { RunStatusPanel } from "./components/RunStatusPanel";
import { CandidateHistory } from "./features/candidate-history/CandidateHistory";
import { ClarificationForm } from "./features/clarifications/ClarificationForm";
import { DesignInputForm } from "./features/design-input/DesignInputForm";
import { EvidenceArtifacts } from "./features/evidence/EvidenceArtifacts";
import { RequirementsPanel } from "./features/requirements/RequirementsPanel";
import { ValidationReport } from "./features/validation-report/ValidationReport";
import { Workspace3D } from "./features/workspace/Workspace3D";
import { artifactUrl } from "./lib/api";
import { useDesignRun } from "./lib/useDesignRun";

export function App() {
  const {
    run,
    events,
    candidates,
    briefArtifact,
    simulation,
    isStarting,
    streamState,
    error,
    start,
    cancel,
    answerClarifications,
  } = useDesignRun();
  const [expert, setExpert] = useState(false);

  const finalRecord =
    (run?.final_candidate_id
      ? candidates.find(
          (record) => record.candidate.candidate_id === run.final_candidate_id,
        )
      : null) ?? candidates.at(-1);
  const metrics = finalRecord?.evaluation?.metrics ?? null;
  const geometryArtifactId = finalRecord?.candidate.geometry_artifact_id ?? null;
  const geometryUrl =
    run && geometryArtifactId ? artifactUrl(run.run_id, geometryArtifactId) : null;

  return (
    <main className="app app-wide">
      <header className="app-header">
        <div className="header-row">
          <div>
            <p className="eyebrow">Mechanism AI</p>
            <h1>Constraint-driven four-bar linkage design</h1>
          </div>
          <div className="view-mode" role="group" aria-label="View mode">
            <button
              type="button"
              className={expert ? "" : "active"}
              aria-pressed={!expert}
              onClick={() => setExpert(false)}
            >
              Beginner
            </button>
            <button
              type="button"
              className={expert ? "active" : ""}
              aria-pressed={expert}
              onClick={() => setExpert(true)}
            >
              Expert
            </button>
          </div>
        </div>
        <p className="lede">
          The AI proposes candidates. An independent evaluator decides whether they pass, using
          fixed criteria and saved evidence. Beginner and Expert views share the same engine and
          evaluation rules.
        </p>
      </header>

      {error ? <p className="banner banner-error">{error}</p> : null}

      <div className="workspace-layout">
        <div className="workspace-column">
          <DesignInputForm onSubmit={start} disabled={isStarting} />
          {run ? (
            <ClarificationForm
              run={run}
              onSubmit={(answers) => void answerClarifications(answers)}
            />
          ) : null}
          <RequirementsPanel briefArtifact={briefArtifact} expert={expert} />
        </div>

        <div className="workspace-column workspace-column-center">
          <Workspace3D
            geometryUrl={geometryUrl}
            geometryArtifactId={geometryArtifactId}
            simulation={simulation}
            brief={briefArtifact}
            metrics={metrics}
          />
          <RunStatusPanel
            run={run}
            events={events}
            streamState={streamState}
            onCancel={() => void cancel()}
            expert={expert}
          />
        </div>

        <div className="workspace-column">
          <ValidationReport
            run={run}
            candidates={candidates}
            simulation={simulation}
            expert={expert}
          />
          <CandidateHistory candidates={candidates} />
          <EvidenceArtifacts run={run} candidates={candidates} expert={expert} />
        </div>
      </div>

      <footer className="app-footer">
        <span>Hackathon MVP scope: planar four-bar linkages, kinematic and geometric checks only.</span>
        <span>Passing checks do not certify manufacturability or physical safety.</span>
      </footer>
    </main>
  );
}
