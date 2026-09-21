const SIZE = 120;
const STROKE = 16;
const R = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * R;

export default function DonutChart({ segments }) {
  // segments: [{ label, value, color }]
  const total = segments.reduce((sum, s) => sum + s.value, 0);

  if (total === 0) {
    return (
      <div className="donut-wrap">
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
          <circle
            cx={SIZE / 2} cy={SIZE / 2} r={R}
            fill="none" stroke="var(--color-border)" strokeWidth={STROKE}
          />
        </svg>
        <div className="donut-center">
          <span className="donut-total">0</span>
          <span className="donut-total-label">tickets</span>
        </div>
      </div>
    );
  }

  let offset = 0;
  const arcs = segments
    .filter((s) => s.value > 0)
    .map((s) => {
      const fraction = s.value / total;
      const len = fraction * CIRCUMFERENCE;
      const arc = (
        <circle
          key={s.label}
          cx={SIZE / 2} cy={SIZE / 2} r={R}
          fill="none" stroke={s.color} strokeWidth={STROKE}
          strokeDasharray={`${len} ${CIRCUMFERENCE - len}`}
          strokeDashoffset={-offset}
          strokeLinecap="butt"
        />
      );
      offset += len;
      return arc;
    });

  return (
    <div className="donut-wrap">
      <svg
        width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ transform: "rotate(-90deg)" }}
      >
        {arcs}
      </svg>
      <div className="donut-center">
        <span className="donut-total">{total}</span>
        <span className="donut-total-label">tickets</span>
      </div>
    </div>
  );
}
