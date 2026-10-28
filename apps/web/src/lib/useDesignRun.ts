import { useCallback, useEffect, useRef, useState } from "react";

import {
  cancelDesignRun,
  createDesignRun,
  getArtifact,
  getDesignRun,
  listCandidates,
  submitClarifications,
  subscribeToRun,
  type BriefArtifact,
  type CandidateRecord,
  type DesignRun,
  type RunEvent,
  type SimulationResult,
  type StreamStatus,
} from "./api";

export type RunStreamState = "idle" | StreamStatus | "ended";

const REFRESH_ON_EVENTS = new Set([
  "run_started",
  "requirements_ready",
  "clarification_required",
  "capability_selected",
  "evaluation_completed",
]);

export interface DesignRunState {
  run: DesignRun | null;
  events: RunEvent[];
  candidates: CandidateRecord[];
  briefArtifact: BriefArtifact | null;
  simulation: SimulationResult | null;
  isStarting: boolean;
  streamState: RunStreamState;
  error: string | null;
  start: (prompt: string, maxCandidates: number) => Promise<void>;
  cancel: () => Promise<void>;
  answerClarifications: (answers: Record<string, string>) => Promise<void>;
}

export function useDesignRun(): DesignRunState {
  const [run, setRun] = useState<DesignRun | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [candidates, setCandidates] = useState<CandidateRecord[]>([]);
  const [briefArtifact, setBriefArtifact] = useState<BriefArtifact | null>(null);
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [streamState, setStreamState] = useState<RunStreamState>("idle");
  const [error, setError] = useState<string | null>(null);
  const unsubscribeRef = useRef<(() => void) | null>(null);
  const streamStateRef = useRef<RunStreamState>("idle");

  const updateStreamState = useCallback((state: RunStreamState) => {
    streamStateRef.current = state;
    setStreamState(state);
  }, []);

  useEffect(() => {
    return () => {
      unsubscribeRef.current?.();
    };
  }, []);

  const refreshSeqRef = useRef(0);

  const refresh = useCallback(async (runId: string) => {
    const seq = ++refreshSeqRef.current;
    try {
      const [latestRun, latestCandidates] = await Promise.all([
        getDesignRun(runId),
        listCandidates(runId),
      ]);
      if (seq !== refreshSeqRef.current) {
        return;
      }
      setRun(latestRun);
      setCandidates(latestCandidates);

      const [latestBrief, latestSimulation] = await Promise.all([
        getArtifact<BriefArtifact>(runId, "brief.json").catch(() => null),
        latestRun.final_candidate_id
          ? getArtifact<SimulationResult>(
              runId,
              `simulation_${latestRun.final_candidate_id}.json`,
            ).catch(() => null)
          : Promise.resolve(null),
      ]);
      if (seq !== refreshSeqRef.current) {
        return;
      }
      setBriefArtifact(latestBrief);
      setSimulation(latestSimulation);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to refresh the design run.");
    }
  }, []);

  const start = useCallback(
    async (prompt: string, maxCandidates: number) => {
      unsubscribeRef.current?.();
      setIsStarting(true);
      setError(null);
      setEvents([]);
      setCandidates([]);
      setBriefArtifact(null);
      setSimulation(null);
      setRun(null);
      updateStreamState("idle");

      try {
        const created = await createDesignRun(prompt, maxCandidates);
        setRun(created);
        unsubscribeRef.current = subscribeToRun(created.run_id, {
          onEvent: (event) => {
            setEvents((current) => [...current, event]);
            if (REFRESH_ON_EVENTS.has(event.event)) {
              // These events change run state (pause, routing, results) without
              // being terminal; re-fetch so the UI never shows stale state.
              void refresh(created.run_id);
            }
          },
          onTerminal: () => {
            updateStreamState("ended");
            void refresh(created.run_id);
          },
          onStatusChange: (status) => {
            const previous = streamStateRef.current;
            if (status === "reconnecting") {
              updateStreamState("reconnecting");
              void refresh(created.run_id);
              return;
            }
            if (previous === "reconnecting") {
              // The server replays the full event history on reconnect, so
              // rebuild the log from the replay instead of appending to a
              // possibly stale one.
              setEvents([]);
            }
            updateStreamState("live");
            if (previous === "reconnecting") {
              void refresh(created.run_id);
            }
          },
        });
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Unable to start the design run.");
      } finally {
        setIsStarting(false);
      }
    },
    [refresh, updateStreamState],
  );

  const cancel = useCallback(async () => {
    if (!run) {
      return;
    }
    try {
      const updated = await cancelDesignRun(run.run_id);
      setRun(updated);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to cancel the design run.");
    }
  }, [run]);

  const answerClarifications = useCallback(
    async (answers: Record<string, string>) => {
      if (!run) {
        return;
      }
      try {
        const updated = await submitClarifications(run.run_id, answers);
        setRun(updated);
      } catch (cause) {
        setError(
          cause instanceof Error ? cause.message : "Unable to submit the clarification answers.",
        );
      }
    },
    [run],
  );

  return {
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
  };
}
