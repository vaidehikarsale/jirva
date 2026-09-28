import { useEffect, useState } from "react";
import { getEvaluation } from "../api";
import { BarChartIcon } from "../icons";
import PageHeader from "../components/PageHeader";
import DistributionList from "../components/DistributionList";
import "./Evaluation.css";

function pct(value) {
  if (value == null) return "-";
  return `${Math.round(value * 100)}%`;
}

function ConfusionMatrix({ matrix }) {
  const expectedLabels = Object.keys(matrix);
  const predictedLabels = Array.from(
    new Set(expectedLabels.flatMap((e) => Object.keys(matrix[e])))
  ).sort();

  return (
    <table className="confusion-table">
      <thead>
        <tr>
          <th>Expected \ Predicted</th>
          {predictedLabels.map((p) => <th key={p}>{p}</th>)}
        </tr>
      </thead>
      <tbody>
        {expectedLabels.map((expected) => (
          <tr key={expected}>
            <td className="confusion-row-label">{expected}</td>
            {predictedLabels.map((predicted) => {
              const count = matrix[expected][predicted] || 0;
              const isMatch = expected === predicted;
              return (
                <td
                  key={predicted}
                  className={isMatch ? "confusion-match" : count > 0 ? "confusion-miss" : ""}
                >
                  {count || (isMatch ? 0 : "")}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CalibrationCard({ result }) {
  return (
    <div className="panel calibration-card">
      <div className="calibration-header">
        <div>
          <h2>{result.name}</h2>
          <p>{result.description}</p>
        </div>
        <div className="calibration-accuracy">
          <span className="calibration-accuracy-value">{pct(result.accuracy)}</span>
          <span className="calibration-accuracy-label">accuracy</span>
        </div>
      </div>
      <p className="calibration-meta">
        {result.total_cases} labeled case{result.total_cases === 1 ? "" : "s"} ·{" "}
        <code>{result.source}</code>
      </p>
      {result.note && <p className="calibration-note">{result.note}</p>}
      <ConfusionMatrix matrix={result.confusion_matrix} />
    </div>
  );
}

export default function Evaluation() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getEvaluation()
      .then(setData)
      .catch((err) => setError(err.message || "Could not load evaluation metrics."));
  }, []);

  return (
    <div className="evaluation-page">
      <PageHeader
        icon={BarChartIcon}
        title="Evaluation"
        description="Calibration accuracy against hand-labeled test sets, plus live operational stats from actual query traffic. These are kept separate deliberately - live traffic has no ground-truth labels, so no accuracy figure is claimed for it."
      />

      {error && <div className="form-error">{error}</div>}
      {!data && !error && <p>Loading...</p>}

      {data && (
        <>
          <section className="evaluation-section">
            <h2 className="evaluation-section-title">Calibration Accuracy</h2>
            <div className="calibration-grid">
              <CalibrationCard result={data.calibration.decision_engine} />
              <CalibrationCard result={data.calibration.domain_guard} />
            </div>
          </section>

          <section className="evaluation-section">
            <h2 className="evaluation-section-title">Live Operational Stats</h2>
            <div className="panel">
              <div className="live-metrics-row">
                <div className="live-metric">
                  <span className="live-metric-value">{data.live.total_tickets}</span>
                  <span className="live-metric-label">Total queries stored</span>
                </div>
                <div className="live-metric">
                  <span className="live-metric-value">
                    {data.live.avg_latency_ms != null ? `${Math.round(data.live.avg_latency_ms)} ms` : "-"}
                  </span>
                  <span className="live-metric-label">Avg latency (recent events)</span>
                </div>
                <div className="live-metric">
                  <span className="live-metric-value">{pct(data.live.recent_error_rate)}</span>
                  <span className="live-metric-label">
                    Error rate ({data.live.recent_events_considered} recent events)
                  </span>
                </div>
              </div>

              <div className="distribution-grid">
                <DistributionList title="Outcome Distribution" distribution={data.live.outcome_distribution} />
                <DistributionList title="Category Distribution" distribution={data.live.category_distribution} />
                <DistributionList title="Risk Distribution" distribution={data.live.risk_distribution} />
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
