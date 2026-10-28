import type { Point2D, SimulationResult } from "../../lib/api";

interface MechanismCanvasProps {
  simulation: SimulationResult | null;
}

const WIDTH = 640;
const HEIGHT = 360;
const PADDING = 52;

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

export function MechanismCanvas({ simulation }: MechanismCanvasProps) {
  const headingHint = simulation
    ? `${simulation.engine} · output point = rocker pin`
    : "Coordinates come from the deterministic reference solver";

  if (!simulation || simulation.samples.length === 0) {
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
                "Run the reference kinematics pipeline to plot the final candidate."}
            </text>
          </g>
        </svg>
      </section>
    );
  }

  const samples = simulation.samples;
  const jointPoints = samples.flatMap((sample) => [
    sample.ground_pivot_a,
    sample.ground_pivot_b,
    sample.crank_pin,
    sample.rocker_pin,
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

  const pose = samples[0];
  const groundA = toSvg(pose.ground_pivot_a);
  const groundB = toSvg(pose.ground_pivot_b);
  const crankPin = toSvg(pose.crank_pin);
  const rockerPin = toSvg(pose.rocker_pin);

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
        aria-label={`Four-bar linkage trace with ${samples.length} samples from the ${simulation.engine} engine`}
      >
        <defs>
          <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M 32 0 L 0 0 0 32" fill="none" stroke="currentColor" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="url(#grid)" opacity="0.18" />

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
            B
          </text>
        </g>

        <g className="legend" transform="translate(18, 18)">
          <line x1={0} y1={0} x2={22} y2={0} className="trace-path" />
          <text x={28} y={4}>output path</text>
          <line x1={0} y1={16} x2={22} y2={16} className="link link-crank" />
          <text x={28} y={20}>crank</text>
          <line x1={0} y1={32} x2={22} y2={32} className="link link-coupler" />
          <text x={28} y={36}>coupler</text>
          <line x1={0} y1={48} x2={22} y2={48} className="link link-rocker" />
          <text x={28} y={52}>rocker</text>
        </g>

        <g className="canvas-caption">
          <text x={18} y={HEIGHT - 18}>
            Pose at {formatNumber(pose.input_angle_deg)}° · {samples.length} samples ·{" "}
            {simulation.engine} {simulation.engine_version}
          </text>
          <text x={WIDTH - 18} y={HEIGHT - 18} textAnchor="end">
            mechanism {formatNumber(spanX)} mm wide · cycle{" "}
            {simulation.cycle_completed ? "complete" : "incomplete"} · collisions{" "}
            {simulation.collision_free ? "none" : "detected"}
          </text>
        </g>
      </svg>
    </section>
  );
}
