import { RunStatusPanel } from "./components/RunStatusPanel";
import { CandidateHistory } from "./features/candidate-history/CandidateHistory";
import { ClarificationForm } from "./features/clarifications/ClarificationForm";
import { DesignInputForm } from "./features/design-input/DesignInputForm";
import { EvidenceArtifacts } from "./features/evidence/EvidenceArtifacts";
import { MechanismCanvas } from "./features/simulation/MechanismCanvas";
import { ValidationReport } from "./features/validation-report/ValidationReport";
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

  const finalRecord =
    (run?.final_candidate_id
      ? candidates.find(
          (record) => record.candidate.candidate_id === run.final_candidate_id,
        )
      : null) ?? candidates.at(-1);
  const metrics = finalRecord?.evaluation?.metrics ?? null;

  return (
    <main className="app">
      <header className="app-header">
        <p className="eyebrow">Mechanism AI</p>
        <h1>Constraint-driven four-bar linkage design</h1>
        <p className="lede">
          The AI proposes candidates. An independent evaluator decides whether they pass, using
          fixed criteria and saved evidence.
        </p>
      </header>

      {error ? <p className="banner banner-error">{error}</p> : null}

      <div className="layout layout-top">
        <DesignInputForm onSubmit={start} disabled={isStarting} />
        <RunStatusPanel run={run} events={events} streamState={streamState} onCancel={() => void cancel()} />
      </div>

      {run ? (
        <ClarificationForm run={run} onSubmit={(answers) => void answerClarifications(answers)} />
      ) : null}

      <div className="layout">
        <MechanismCanvas simulation={simulation} brief={briefArtifact} metrics={metrics} />
        <ValidationReport
          run={run}
          candidates={candidates}
          briefArtifact={briefArtifact}
          simulation={simulation}
        />
      </div>

      <CandidateHistory candidates={candidates} />
      <EvidenceArtifacts run={run} candidates={candidates} />

      <footer className="app-footer">
        <span>Hackathon MVP scope: planar four-bar linkages, kinematic and geometric checks only.</span>
        <span>Passing checks do not certify manufacturability or physical safety.</span>
      </footer>
    </main>
  );
}
