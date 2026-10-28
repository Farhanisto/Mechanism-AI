import type { DesignRun, RunEvent } from "../lib/api";
import type { RunStreamState } from "../lib/useDesignRun";

interface RunStatusPanelProps {
  run: DesignRun | null;
  events: RunEvent[];
  streamState: RunStreamState;
}

const STREAM_LABELS: Record<RunStreamState, string | null> = {
  idle: null,
  live: "live stream",
  reconnecting: "reconnecting",
  ended: "stream closed",
};

function describeEvent(event: RunEvent): string {
  const fields = ["stage", "status", "candidate_id", "error_code", "message"] as const;
  const parts = fields
    .map((field) => event.data[field])
    .filter((value): value is string | number => value !== undefined && value !== null)
    .map(String);
  return parts.join(" · ");
}

export function RunStatusPanel({ run, events, streamState }: RunStatusPanelProps) {
  const streamLabel = STREAM_LABELS[streamState];
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Run status</h2>
        <div className="pill-group">
          {streamLabel ? (
            <span
              className={`pill pill-stream-${streamState}`}
              title={
                streamState === "reconnecting"
                  ? "The progress stream dropped; the run state is being re-fetched so no stale result is shown."
                  : undefined
              }
            >
              {streamLabel}
            </span>
          ) : null}
          {run ? (
            <>
              <span className={`pill pill-${run.status}`}>{run.status}</span>
              {run.no_pass ? <span className="pill pill-failed">no pass</span> : null}
            </>
          ) : null}
        </div>
      </div>

      {streamState === "reconnecting" ? (
        <p className="notice notice-warning">
          <strong>Reconnecting</strong>
          <span>
            The progress stream dropped. The run state shown here is re-fetched from the server,
            so it is never presented as a fresh success while the stream is down.
          </span>
        </p>
      ) : null}

      {run ? (
        <dl className="run-meta">
          <div>
            <dt>Run</dt>
            <dd>{run.run_id}</dd>
          </div>
          <div>
            <dt>Stage</dt>
            <dd>{run.stage}</dd>
          </div>
          <div>
            <dt>Outcome</dt>
            <dd>
              {run.status === "completed"
                ? run.no_pass
                  ? "no pass"
                  : "passed"
                : run.status}
            </dd>
          </div>
          <div>
            <dt>Error</dt>
            <dd>{run.error_code ?? "none"}</dd>
          </div>
        </dl>
      ) : (
        <p className="empty-state">Start a design run to stream progress events.</p>
      )}

      <ol className="event-log">
        {events.map((event, index) => (
          <li key={`${event.event}-${index}`}>
            <code>{event.event}</code>
            <span>{describeEvent(event)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
