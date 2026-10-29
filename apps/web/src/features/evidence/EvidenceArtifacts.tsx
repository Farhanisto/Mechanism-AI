import { useState } from "react";

import {
  artifactUrl,
  getArtifact,
  type CandidateRecord,
  type DesignRun,
} from "../../lib/api";

interface EvidenceArtifactsProps {
  run: DesignRun | null;
  candidates: CandidateRecord[];
}

type ArtifactState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; payload: unknown }
  | { status: "error"; message: string };

export function EvidenceArtifacts({ run, candidates }: EvidenceArtifactsProps) {
  const [artifacts, setArtifacts] = useState<Record<string, ArtifactState>>({});

  if (!run) {
    return null;
  }

  const names = [
    "run.json",
    "brief.json",
    "candidates.json",
    ...candidates.map(
      (record) => `simulation_${record.candidate.candidate_id}.json`,
    ),
    ...candidates
      .map((record) => record.candidate.geometry_artifact_id)
      .filter((name): name is string => Boolean(name)),
    "evidence.json",
    ...(run.error_code ? ["error.json"] : []),
  ];

  const load = async (name: string): Promise<unknown> => {
    const existing = artifacts[name];
    if (existing?.status === "loaded") {
      return existing.payload;
    }
    setArtifacts((current) => ({ ...current, [name]: { status: "loading" } }));
    try {
      const payload = await getArtifact<unknown>(run.run_id, name);
      setArtifacts((current) => ({ ...current, [name]: { status: "loaded", payload } }));
      return payload;
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Unable to load the artifact.";
      setArtifacts((current) => ({ ...current, [name]: { status: "error", message } }));
      throw new Error(message);
    }
  };

  const download = async (name: string) => {
    try {
      const payload = await load(name);
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = name;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      // The per-artifact error state is already rendered.
    }
  };

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Evidence artifacts</h2>
        <span className="panel-hint">Persisted JSON for this run; server-side evidence is authoritative</span>
      </div>
      <ul className="artifact-list">
        {names.map((name) => {
          const state = artifacts[name] ?? { status: "idle" as const };
          if (!name.endsWith(".json")) {
            return (
              <li key={name} className="artifact-item">
                <span className="artifact-binary">
                  <code>{name}</code>
                </span>
                <a
                  className="artifact-download"
                  href={artifactUrl(run.run_id, name)}
                  download={name}
                >
                  Download
                </a>
              </li>
            );
          }
          return (
            <li key={name} className="artifact-item">
              <details
                onToggle={(event) => {
                  if ((event.target as HTMLDetailsElement).open) {
                    void load(name);
                  }
                }}
              >
                <summary>
                  <code>{name}</code>
                </summary>
                {state.status === "loading" ? <p className="empty-state">Loading…</p> : null}
                {state.status === "error" ? (
                  <p className="notice notice-error">{state.message}</p>
                ) : null}
                {state.status === "loaded" ? (
                  <pre className="artifact-json">{JSON.stringify(state.payload, null, 2)}</pre>
                ) : null}
              </details>
              <button
                type="button"
                className="artifact-download"
                onClick={() => void download(name)}
              >
                Download
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
