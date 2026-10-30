import type { SimulationResult } from "../../lib/api";

interface OutputAnglePlotProps {
  simulation: SimulationResult;
}

const WIDTH = 520;
const HEIGHT = 150;
const PADDING = 26;

export function outputAngles(simulation: SimulationResult): number[] {
  const angles = simulation.samples.map((sample) => {
    const pivot = sample.ground_pivot_b;
    return (
      (Math.atan2(
        sample.rocker_pin.y - pivot.y,
        sample.rocker_pin.x - pivot.x,
      ) *
        180) /
      Math.PI
    );
  });
  const unwrapped: number[] = [];
  for (const angle of angles) {
    if (unwrapped.length === 0) {
      unwrapped.push(angle);
      continue;
    }
    let current = angle;
    const previous = unwrapped[unwrapped.length - 1];
    while (current - previous > 180) current -= 360;
    while (current - previous < -180) current += 360;
    unwrapped.push(current);
  }
  return unwrapped;
}

export function OutputAnglePlot({ simulation }: OutputAnglePlotProps) {
  if (simulation.samples.length < 2) {
    return null;
  }
  const angles = outputAngles(simulation);
  const min = Math.min(...angles);
  const max = Math.max(...angles);
  const span = Math.max(max - min, 1e-6);
  const points = angles
    .map((angle, index) => {
      const x = PADDING + ((WIDTH - 2 * PADDING) * index) / (angles.length - 1);
      const y = HEIGHT - PADDING - ((HEIGHT - 2 * PADDING) * (angle - min)) / span;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="angle-plot">
      <p className="mode-note">
        Output (rocker) angle over one cycle · measured sweep {span.toFixed(1)}°
      </p>
      <svg
        className="angle-plot-svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Output angle over one cycle with a ${span.toFixed(1)} degree sweep`}
      >
        <line
          x1={PADDING}
          y1={HEIGHT - PADDING}
          x2={WIDTH - PADDING}
          y2={HEIGHT - PADDING}
          className="angle-axis"
        />
        <line
          x1={PADDING}
          y1={PADDING}
          x2={PADDING}
          y2={HEIGHT - PADDING}
          className="angle-axis"
        />
        <polyline points={points} className="angle-line" />
        <text x={PADDING} y={PADDING - 8} className="dimension-label">
          {max.toFixed(1)}°
        </text>
        <text x={PADDING} y={HEIGHT - PADDING + 14} className="dimension-label">
          {min.toFixed(1)}°
        </text>
      </svg>
    </div>
  );
}
