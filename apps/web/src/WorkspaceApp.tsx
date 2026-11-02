import { ArrowLeft, CheckCircle2, FlaskConical, Layers3, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

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
import { artifactUrl, getArtifact, getHealth, type SimulationResult } from "./lib/api";
import {
  buildAttempts,
  isAttemptInProgress,
  type AttemptStatus,
} from "./lib/attempts";
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

const ATTEMPT_STATUS_LABEL: Record<AttemptStatus, string> = {
  queued: "queued",
  modeling: "waiting for the model",
  compiling: "building CAD geometry",
  simulating: "simulating the mechanism",
  evaluating: "evaluating the attempt",
  passed: "passed",
  failed: "failed",
};

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

  useEffect(() => {
    if (run?.status === "awaiting_clarification") {
      // On phones the brief column is hidden on other tabs; never leave a paused
      // run without showing the questions.
      setMobileSection("brief");
    }
  }, [run?.status]);

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
  const attempts = useMemo(
    () => buildAttempts({ events, programs, candidates }),
    [events, programs, candidates],
  );
  const latestAttemptWithArtifact =
    [...attempts].reverse().find((attempt) => attempt.artifactId) ?? null;
  const [selectedAttemptNumber, setSelectedAttemptNumber] = useState<number | null>(null);
  const [followLatest, setFollowLatest] = useState(true);
  const [attemptSimulation, setAttemptSimulation] = useState<SimulationResult | null>(null);
  const runIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (run?.run_id !== runIdRef.current) {
      runIdRef.current = run?.run_id ?? null;
      setFollowLatest(true);
      setSelectedAttemptNumber(null);
      setAttemptSimulation(null);
    }
  }, [run?.run_id]);

  useEffect(() => {
    if (!followLatest || !latestAttemptWithArtifact) {
      return;
    }
    setSelectedAttemptNumber(latestAttemptWithArtifact.attemptNumber);
  }, [
    followLatest,
    latestAttemptWithArtifact?.attemptNumber,
    latestAttemptWithArtifact?.artifactId,
  ]);

  useEffect(() => {
    if (
      !followLatest ||
      !run?.final_candidate_id ||
      run.status !== "completed" &&
      run.status !== "failed"
    ) {
      return;
    }
    const finalAttempt = attempts.find(
      (attempt) => attempt.candidateId === run.final_candidate_id,
    );
    if (finalAttempt) {
      setSelectedAttemptNumber(finalAttempt.attemptNumber);
    }
  }, [followLatest, run?.status, run?.final_candidate_id, attempts]);

  const activeAttempt =
    (selectedAttemptNumber != null
      ? attempts.find((attempt) => attempt.attemptNumber === selectedAttemptNumber)
      : null) ?? latestAttemptWithArtifact;

  useEffect(() => {
    if (!run || !activeAttempt?.candidateId || !activeAttempt.hasSimulation) {
      setAttemptSimulation(null);
      return;
    }
    if (activeAttempt.candidateId === run.final_candidate_id && simulation) {
      setAttemptSimulation(simulation);
      return;
    }
    let cancelled = false;
    getArtifact<SimulationResult>(
      run.run_id,
      `simulation_${activeAttempt.candidateId}.json`,
    )
      .then((payload) => {
        if (!cancelled) {
          setAttemptSimulation(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAttemptSimulation(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [run?.run_id, run?.final_candidate_id, activeAttempt?.candidateId, activeAttempt?.hasSimulation, simulation]);

  const activeArtifactId = activeAttempt?.artifactId ?? geometryArtifactId;
  const activeGeometryUrl =
    run && activeArtifactId ? artifactUrl(run.run_id, activeArtifactId) : null;
  const activeVerified = activeAttempt
    ? activeAttempt.status === "passed"
    : geometryVerified;
  const workspaceSimulation = activeAttempt ? attemptSimulation : simulation;

  const isRunning = run?.status === "running" || run?.status === "queued";
  const liveAttempt = attempts.find(isAttemptInProgress) ?? null;
  const lastAttempt = attempts.at(-1) ?? null;
  const liveLabel = !isRunning
    ? null
    : liveAttempt
      ? `Attempt ${liveAttempt.attemptNumber} · ${ATTEMPT_STATUS_LABEL[liveAttempt.status]}…`
      : lastAttempt?.status === "passed"
        ? "Finalizing the validated design…"
        : attempts.length > 0
          ? `Attempt ${lastAttempt?.attemptNumber ?? attempts.length} failed · preparing the next attempt…`
          : "Interpreting the brief with the model…";

  const handleStart = (prompt: string, maxCandidates: number) => {
    setMobileSection("model");
    start(prompt, maxCandidates);
  };

  const pendingQuestions = run?.pending_clarifications.length ?? 0;
  const needsClarification = run?.status === "awaiting_clarification";
  const scrollToClarifications = () => {
    setMobileSection("brief");
    const panel = document.querySelector(".clarification-panel");
    panel?.scrollIntoView({ behavior: "smooth", block: "center" });
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
              {(section.id === "results" && resultsReady) ||
            (section.id === "brief" && needsClarification) ? (
              <span
                className="demo-mobile-dot"
                aria-label={section.id === "brief" ? "questions waiting" : "results available"}
              />
            ) : null}
            </button>
          ))}
        </nav>

        {needsClarification ? (
          <div className="demo-clarification-banner" role="status">
            <div>
              <strong>Run paused for clarification</strong>
              <span>
                {pendingQuestions} question{pendingQuestions === 1 ? "" : "s"} need an answer
                before candidates are generated.
              </span>
            </div>
            <button type="button" onClick={scrollToClarifications}>
              Answer questions
            </button>
          </div>
        ) : null}

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
              geometryUrl={activeGeometryUrl}
              geometryArtifactId={activeArtifactId}
              verified={activeVerified}
              attemptCount={programs.length}
              simulation={workspaceSimulation}
              brief={briefArtifact}
              metrics={metrics}
              attempts={attempts}
              activeAttemptNumber={activeAttempt?.attemptNumber ?? null}
              onSelectAttempt={(attemptNumber) => {
                setFollowLatest(false);
                setSelectedAttemptNumber(attemptNumber);
              }}
              followLatest={followLatest}
              onFollowLatest={() => setFollowLatest(true)}
              liveLabel={liveLabel}
              isRunning={isRunning}
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
