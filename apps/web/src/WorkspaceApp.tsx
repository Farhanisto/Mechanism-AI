import { ArrowLeft, CheckCircle2, FlaskConical, Layers3, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { RunStatusPanel } from "./components/RunStatusPanel";
import { CandidateHistory } from "./features/candidate-history/CandidateHistory";
import { ClarificationForm } from "./features/clarifications/ClarificationForm";
import { DesignInputForm } from "./features/design-input/DesignInputForm";
import { EvidenceArtifacts } from "./features/evidence/EvidenceArtifacts";
import { ProgramsPanel } from "./features/programs/ProgramsPanel";
import { RequirementsPanel } from "./features/requirements/RequirementsPanel";
import { ValidationReport } from "./features/validation-report/ValidationReport";
import { Workspace3D } from "./features/workspace/Workspace3D";
import { Brand } from "./landing/Brand";
import { artifactUrl, getHealth } from "./lib/api";
import { useDesignRun } from "./lib/useDesignRun";
import "./demo.css";

type MobileSection = "brief" | "model" | "results";

const MOBILE_SECTIONS: { id: MobileSection; label: string }[] = [
  { id: "brief", label: "Brief" },
  { id: "model", label: "Model" },
  { id: "results", label: "Results" },
];

const DEMO_HIGHLIGHTS = [
  { icon: FlaskConical, label: "Deterministic checks" },
  { icon: Layers3, label: "CAD + motion artifacts" },
  { icon: ShieldCheck, label: "Evidence bundle" },
];

export function WorkspaceApp() {
  const {
    run,
    events,
    candidates,
    briefArtifact,
    partBrief,
    programs,
    simulation,
    isStarting,
    streamState,
    error,
    start,
    cancel,
    answerClarifications,
  } = useDesignRun();
  const [expert, setExpert] = useState(false);
  const [mobileSection, setMobileSection] = useState<MobileSection>("brief");
  const [aiEnabled, setAiEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    document.body.classList.add("demo-body");
    return () => document.body.classList.remove("demo-body");
  }, []);

  useEffect(() => {
    let active = true;
    getHealth()
      .then((health) => {
        if (active) {
          setAiEnabled(health.ai_enabled ?? null);
        }
      })
      .catch(() => null);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const started = events.find((event) => event.event === "run_started");
    if (started && typeof started.data.ai_enabled === "boolean") {
      setAiEnabled(started.data.ai_enabled);
    }
  }, [events]);

  const finalRecord =
    (run?.final_candidate_id
      ? candidates.find(
          (record) => record.candidate.candidate_id === run.final_candidate_id,
        )
      : null) ?? candidates.at(-1);
  const metrics = finalRecord?.evaluation?.metrics ?? null;
  const bestProgram =
    programs.find((record) => record.evaluation?.status === "passed") ??
    programs.at(-1) ??
    null;
  const geometryVerified = Boolean(
    finalRecord?.evaluation?.status === "passed" ||
      bestProgram?.evaluation?.status === "passed",
  );
  const geometryArtifactId =
    finalRecord?.candidate.geometry_artifact_id ??
    bestProgram?.geometry_artifact_id ??
    null;
  const geometryUrl =
    run && geometryArtifactId ? artifactUrl(run.run_id, geometryArtifactId) : null;

  const handleStart = (prompt: string, maxCandidates: number) => {
    setMobileSection("model");
    start(prompt, maxCandidates);
  };

  const resultsReady = Boolean(
    run &&
      (candidates.length > 0 ||
        programs.length > 0 ||
        run.status === "completed" ||
        run.status === "failed"),
  );

  return (
    <div className="demo-app">
      <header className="demo-topbar">
        <a className="demo-brand" href="#/" aria-label="Back to the Mechanism AI website">
          <Brand />
        </a>
        <span className="demo-crumb">Engineering workspace</span>
        <div className="demo-topbar-right">
          {run ? (
            <span className={`demo-run-state demo-run-${run.status}`}>
              <span className="demo-run-dot" />
              {run.status.replace("_", " ")}
            </span>
          ) : (
            <span className="demo-run-state demo-run-idle">
              <span className="demo-run-dot" />
              ready
            </span>
          )}
          <a className="demo-back" href="#/" aria-label="Exit demo and return to the website">
            <ArrowLeft size={16} />
          </a>
          <div className="demo-view-toggle" role="group" aria-label="View mode">
            <button
              type="button"
              className={expert ? "" : "is-active"}
              aria-pressed={!expert}
              onClick={() => setExpert(false)}
            >
              Beginner
            </button>
            <button
              type="button"
              className={expert ? "is-active" : ""}
              aria-pressed={expert}
              onClick={() => setExpert(true)}
            >
              Expert
            </button>
          </div>
          <a className="demo-exit" href="#/">
            Exit demo
          </a>
        </div>
      </header>

      <main className="demo-main">
        <section className="demo-intro">
          <div className="demo-intro-copy">
            <span className="demo-eyebrow">Design studio</span>
            <h1>Constraint-driven design</h1>
            <p>
              Describe a mechanism in plain language. The AI proposes candidates and an
              independent evaluator decides what passes, using saved evidence.
            </p>
          </div>
          <ul className="demo-highlights">
            {DEMO_HIGHLIGHTS.map(({ icon: Icon, label }) => (
              <li key={label}>
                <Icon size={14} />
                {label}
              </li>
            ))}
          </ul>
        </section>

        <nav className="demo-mobile-nav" aria-label="Workspace sections">
          {MOBILE_SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              className={mobileSection === section.id ? "is-active" : ""}
              aria-pressed={mobileSection === section.id}
              onClick={() => {
                setMobileSection(section.id);
                try {
                  window.scrollTo({ top: 0, behavior: "smooth" });
                } catch {
                  window.scrollTo(0, 0);
                }
              }}
            >
              {section.label}
              {section.id === "results" && resultsReady ? (
                <span className="demo-mobile-dot" aria-label="results available" />
              ) : null}
            </button>
          ))}
        </nav>

        {aiEnabled === false ? (
          <div className="demo-notice" role="status">
            <strong>AI model disabled</strong>
            <span>
              This API has no Meta key configured, so runs use the deterministic fallback.
              Set MECHANISM_AI_META_API_KEY on the API service to enable model-authored
              design.
            </span>
          </div>
        ) : null}

        {error ? (
          <p className="demo-error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="demo-grid">
          <div
            className={`demo-col demo-col-brief${
              mobileSection === "brief" ? " is-active" : ""
            }`}
          >
            <DesignInputForm onSubmit={handleStart} disabled={isStarting} />
            {run ? (
              <ClarificationForm
                run={run}
                onSubmit={(answers) => void answerClarifications(answers)}
              />
            ) : null}
            <RequirementsPanel
              briefArtifact={briefArtifact}
              partBrief={partBrief}
              capabilityId={run?.capability_id ?? null}
              expert={expert}
            />
          </div>

          <div
            className={`demo-col demo-col-model${
              mobileSection === "model" ? " is-active" : ""
            }`}
          >
            <Workspace3D
              geometryUrl={geometryUrl}
              geometryArtifactId={geometryArtifactId}
              verified={geometryVerified}
              attemptCount={programs.length}
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

          <div
            className={`demo-col demo-col-results${
              mobileSection === "results" ? " is-active" : ""
            }`}
          >
            <ValidationReport
              run={run}
              candidates={candidates}
              programs={programs}
              simulation={simulation}
              expert={expert}
            />
            {candidates.length > 0 || programs.length === 0 ? (
              <CandidateHistory candidates={candidates} />
            ) : null}
            <ProgramsPanel runId={run?.run_id ?? null} programs={programs} expert={expert} />
            <EvidenceArtifacts run={run} candidates={candidates} expert={expert} />
          </div>
        </div>

        <footer className="demo-footer">
          <span>
            <CheckCircle2 size={13} /> Planar four-bar linkages and model-authored CAD programs.
          </span>
          <span>Passing checks do not certify manufacturability or physical safety.</span>
        </footer>
      </main>
    </div>
  );
}
