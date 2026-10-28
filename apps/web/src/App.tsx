import { RunStatusPanel } from "./components/RunStatusPanel";
import { CandidateHistory } from "./features/candidate-history/CandidateHistory";
import { DesignInputForm } from "./features/design-input/DesignInputForm";
import { MechanismCanvas } from "./features/simulation/MechanismCanvas";
import { ValidationReport } from "./features/validation-report/ValidationReport";
import { useDesignRun } from "./lib/useDesignRun";

export function App() {
  const { run, events, candidates, briefArtifact, simulation, isStarting, error, start } =
    useDesignRun();

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
        <RunStatusPanel run={run} events={events} />
      </div>

      <div className="layout">
        <MechanismCanvas simulation={simulation} />
        <ValidationReport
          run={run}
          candidates={candidates}
          briefArtifact={briefArtifact}
        />
      </div>

      <CandidateHistory candidates={candidates} />

      <footer className="app-footer">
        <span>Hackathon MVP scope: planar four-bar linkages, kinematic and geometric checks only.</span>
        <span>Passing checks do not certify manufacturability or physical safety.</span>
      </footer>
    </main>
  );
}
