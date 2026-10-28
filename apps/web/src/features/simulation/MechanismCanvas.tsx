import { useEffect, useState } from "react";

import type {
  BriefArtifact,
  CandidateMetrics,
  Point2D,
  SimulationResult,
} from "../../lib/api";

interface MechanismCanvasProps {
  simulation: SimulationResult | null;
  brief: BriefArtifact | null;
  metrics: CandidateMetrics | null;
}

const WIDTH = 640;
const HEIGHT = 360;
const PADDING = 52;
const FRAME_MS = 40;

function toSvgPoint(
  point: Point2D,
  scale: number,
  offsetX: number,
  offsetY: number,
): { x: number; y: number } {
  return {
    x: offsetX + point.x * scale,
    y: offsetY - point.y * scale,
  };
}

function formatNumber(value: number): string {
  return value.toFixed(1);
}

export function MechanismCanvas({ simulation, brief, metrics }: MechanismCanvasProps) {
  const samples = simulation?.samples ?? [];
  const sampleCount = samples.length;
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    setFrame(0);
    setPlaying(sampleCount > 0);
  }, [simulation, sampleCount]);

  useEffect(() => {
    if (!playing || sampleCount === 0) {
      return;
    }
    const timer = setInterval(() => {
      setFrame((current) => (current + 1) % sampleCount);
    }, FRAME_MS);
    return () => clearInterval(timer);
  }, [playing, sampleCount]);

  const headingHint = simulation
    ? `${simulation.engine} · output point = rocker pin`
    : "Coordinates come from the persisted simulation trace";

  if (!simulation || sampleCount === 0) {
    return (
      <section className="panel">
        <div className="panel-heading">
          <h2>Simulation trace</h2>
          <span className="panel-hint">{headingHint}</span>
        </div>
        <svg
          className="canvas"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label="Mechanism visualization waiting for a valid simulation trace"
        >
          <defs>
            <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="currentColor" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width={WIDTH} height={HEIGHT} fill="url(#grid)" opacity="0.18" />
          <g className="canvas-empty">
            <text x={WIDTH / 2} y={HEIGHT / 2 - 12} textAnchor="middle">
              {simulation ? "No valid trajectory" : "No trajectory yet"}
            </text>
            <text x={WIDTH / 2} y={HEIGHT / 2 + 16} textAnchor="middle" className="canvas-subtext">
              {simulation?.failure_reason ??
                "Run the design pipeline to plot the final candidate."}
            </text>
          </g>
        </svg>
      </section>
    );
  }

  const jointPoints = samples.flatMap((sample) => [
    sample.ground_pivot_a,
    sample.ground_pivot_b,
    sample.crank_pin,
    sample.rocker_pin,
    sample.output_point,
  ]);
  const minX = Math.min(...jointPoints.map((point) => point.x));
  const maxX = Math.max(...jointPoints.map((point) => point.x));
  const minY = Math.min(...jointPoints.map((point) => point.y));
  const maxY = Math.max(...jointPoints.map((point) => point.y));
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const scale = Math.min(
    (WIDTH - 2 * PADDING) / spanX,
    (HEIGHT - 2 * PADDING - 24) / spanY,
  );
  const offsetX = (WIDTH - spanX * scale) / 2 - minX * scale;
  const offsetY = (HEIGHT - spanY * scale) / 2 + maxY * scale;

  const toSvg = (point: Point2D) => toSvgPoint(point, scale, offsetX, offsetY);
  const outputPath = samples
    .map((sample) => {
      const point = toSvg(sample.output_point);
      return `${point.x.toFixed(2)},${point.y.toFixed(2)}`;
    })
    .join(" ");

  const current = samples[Math.min(frame, sampleCount - 1)];
  const pose = current;
  const groundA = toSvg(pose.ground_pivot_a);
  const groundB = toSvg(pose.ground_pivot_b);
  const crankPin = toSvg(pose.crank_pin);
  const rockerPin = toSvg(pose.rocker_pin);
  const outputNow = toSvg(pose.output_point);

  const target = brief?.brief.target_motion ?? null;
  const constraints = brief?.brief.constraints ?? null;
  const centerMm = { x: minX + spanX / 2, y: minY + spanY / 2 };
  const targetLine = target
    ? {
        from: toSvg({ x: centerMm.x - target.travel_distance / 2, y: centerMm.y }),
        to: toSvg({ x: centerMm.x + target.travel_distance / 2, y: centerMm.y }),
        bandTop: toSvg({ x: minX, y: centerMm.y + target.trajectory_tolerance }).y,
        bandBottom: toSvg({ x: minX, y: centerMm.y - target.trajectory_tolerance }).y,
      }
    : null;

  const dimensionY = toSvg({ x: minX, y: minY }).y + 26;
  const dimensionLeft = toSvg({ x: minX, y: minY }).x;
  const dimensionRight = toSvg({ x: maxX, y: minY }).x;
  const footprintLabel = metrics
    ? `footprint ${formatNumber(metrics.footprint_mm)} mm${
        constraints ? ` (limit ${formatNumber(constraints.max_footprint)} mm)` : ""
      }`
    : `mechanism ${formatNumber(spanX)} mm wide`;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Simulation trace</h2>
        <span className="panel-hint">{headingHint}</span>
      </div>
      <svg
        className="canvas"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Four-bar linkage trace with ${sampleCount} samples from the ${simulation.engine} engine`}
      >
        <defs>
          <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M 32 0 L 0 0 0 32" fill="none" stroke="currentColor" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="url(#grid)" opacity="0.18" />

        {targetLine ? (
          <g>
            <rect
              x={dimensionLeft}
              y={Math.min(targetLine.bandTop, targetLine.bandBottom)}
              width={Math.max(dimensionRight - dimensionLeft, 1)}
              height={Math.abs(targetLine.bandTop - targetLine.bandBottom)}
              className="tolerance-band"
            />
            <line
              x1={targetLine.from.x}
              y1={targetLine.from.y}
              x2={targetLine.to.x}
              y2={targetLine.to.y}
              className="target-path"
            />
            <text
              x={targetLine.to.x}
              y={targetLine.to.y - 8}
              textAnchor="end"
              className="dimension-label"
            >
              requested {formatNumber(target!.travel_distance)} mm near-horizontal
              {target ? ` ±${formatNumber(target.trajectory_tolerance)} mm` : ""}
            </text>
          </g>
        ) : null}

        <line
          x1={groundA.x}
          y1={groundA.y}
          x2={groundB.x}
          y2={groundB.y}
          className="ground-link"
        />
        <polyline points={outputPath} className="trace-path" />

        <line
          x1={groundA.x}
          y1={groundA.y}
          x2={crankPin.x}
          y2={crankPin.y}
          className="link link-crank"
        />
        <line
          x1={crankPin.x}
          y1={crankPin.y}
          x2={rockerPin.x}
          y2={rockerPin.y}
          className="link link-coupler"
        />
        <line
          x1={groundB.x}
          y1={groundB.y}
          x2={rockerPin.x}
          y2={rockerPin.y}
          className="link link-rocker"
        />

        <circle cx={groundA.x} cy={groundA.y} r={6} className="joint" />
        <circle cx={groundB.x} cy={groundB.y} r={6} className="joint" />
        <circle cx={crankPin.x} cy={crankPin.y} r={6} className="joint" />
        <circle cx={rockerPin.x} cy={rockerPin.y} r={7} className="joint joint-output" />
        <circle cx={outputNow.x} cy={outputNow.y} r={4} className="output-marker" />

        <g className="joint-label">
          <text x={groundA.x - 10} y={groundA.y + 19} textAnchor="end">
            O2
          </text>
          <text x={groundB.x + 10} y={groundB.y + 19}>
            O4
          </text>
          <text x={crankPin.x + 9} y={crankPin.y - 8}>
            A
          </text>
          <text x={rockerPin.x + 9} y={rockerPin.y - 8}>
            B (output)
          </text>
        </g>

        <g className="dimension">
          <line x1={dimensionLeft} y1={dimensionY} x2={dimensionRight} y2={dimensionY} />
          <line x1={dimensionLeft} y1={dimensionY - 5} x2={dimensionLeft} y2={dimensionY + 5} />
          <line x1={dimensionRight} y1={dimensionY - 5} x2={dimensionRight} y2={dimensionY + 5} />
          <text
            x={(dimensionLeft + dimensionRight) / 2}
            y={dimensionY + 16}
            textAnchor="middle"
            className="dimension-label"
          >
            {footprintLabel}
          </text>
        </g>

        <g className="legend" transform="translate(18, 18)">
          <line x1={0} y1={0} x2={22} y2={0} className="trace-path" />
          <text x={28} y={4}>actual output path</text>
          <line x1={0} y1={16} x2={22} y2={16} className="target-path" />
          <text x={28} y={20}>requested path</text>
          <rect x={0} y={30} width={22} height={8} className="tolerance-band" />
          <text x={28} y={38}>tolerance band</text>
          <line x1={0} y1={54} x2={22} y2={54} className="link link-crank" />
          <text x={28} y={58}>crank</text>
          <line x1={0} y1={70} x2={22} y2={70} className="link link-coupler" />
          <text x={28} y={74}>coupler</text>
          <line x1={0} y1={86} x2={22} y2={86} className="link link-rocker" />
          <text x={28} y={90}>rocker</text>
        </g>

        <g className="canvas-caption">
          <text x={18} y={HEIGHT - 18}>
            Pose at {formatNumber(pose.input_angle_deg)}° · sample {Math.min(frame, sampleCount - 1) + 1}/
            {sampleCount} · {simulation.engine} {simulation.engine_version}
          </text>
          <text x={WIDTH - 18} y={HEIGHT - 18} textAnchor="end">
            cycle {simulation.cycle_completed ? "complete" : "incomplete"} · collisions{" "}
            {simulation.collision_free ? "none" : "detected"}
          </text>
        </g>
      </svg>

      <div className="playback-controls">
        <button type="button" onClick={() => setPlaying((value) => !value)}>
          {playing ? "Pause" : "Play"}
        </button>
        <input
          type="range"
          min={0}
          max={sampleCount - 1}
          value={Math.min(frame, sampleCount - 1)}
          onChange={(event) => {
            setPlaying(false);
            setFrame(Number(event.target.value));
          }}
          aria-label="Scrub through the computed motion"
        />
        <span className="playback-readout">
          θ = {formatNumber(pose.input_angle_deg)}°
          {metrics ? ` · travel ${formatNumber(metrics.travel_distance_mm)} mm` : ""}
        </span>
      </div>
    </section>
  );
}
