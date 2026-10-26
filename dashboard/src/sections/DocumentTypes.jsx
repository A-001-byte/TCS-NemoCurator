import { useState } from "react";
import { CircleCheck, X } from "lucide-react";
import { Bar, SectionHeader } from "../components/common";
import { fmt, share } from "../format";

const ROWS_SHOWN = 8;

const label = (type) => String(type).replaceAll("_", " ");

function Result({ row }) {
  if (!row.scored) return <span className="badge badge-info">Not scored</span>;
  return row.correct ? (
    <span className="badge badge-success">
      <CircleCheck size={14} /> Correct
    </span>
  ) : (
    <span className="badge">
      <X size={14} /> Wrong
    </span>
  );
}

export default function DocumentTypes({ report }) {
  const [showAll, setShowAll] = useState(false);
  const { accuracy, majority_baseline: baseline, confident, flagged } = report;
  const descriptions = report.type_descriptions || {};
  const rows = showAll ? report.per_document : report.per_document.slice(0, ROWS_SHOWN);

  const metrics = [
    {
      label: "Right, whole family held out",
      value: share(accuracy.by_family),
      note: `${fmt(report.n_scored)} documents scored; each one's near-copies were hidden from the classifier too`,
    },
    {
      label: "Always guessing the biggest type",
      value: share(baseline),
      note: "The score to beat",
    },
    {
      label: "Only the document held out",
      value: share(accuracy.by_document),
      note: "Optimistic: its near-copies stay in training",
    },
    {
      label: "Confident answers",
      value: fmt(confident?.count),
      note: `${share(confident?.accuracy)} right; ${fmt(flagged?.count)} flagged low confidence, ${share(flagged?.accuracy)} right`,
    },
  ];

  return (
    <section id="doctypes" className="section">
      <SectionHeader title="Document types" description={report.caption} />

      <div className="metric-grid">
        {metrics.map((m) => (
          <article className="card metric" key={m.label}>
            <p className="metric-label">{m.label}</p>
            <p className="metric-value">{m.value}</p>
            <p className="metric-note">{m.note}</p>
          </article>
        ))}
      </div>

      {report.variants_note && (
        <div className="callout">
          <p>{report.variants_note}</p>
        </div>
      )}

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Type</th>
                <th className="right">Documents</th>
                <th className="right">Scored</th>
                <th className="w-bar">Found when held out</th>
              </tr>
            </thead>
            <tbody>
              {report.per_type.map((type) => (
                <tr key={type.label}>
                  <td>
                    <p className="cell-title">{label(type.label)}</p>
                    {descriptions[type.label] && <p className="cell-sub">{descriptions[type.label]}</p>}
                  </td>
                  <td className="right num">{fmt(type.documents)}</td>
                  <td className="right num">{fmt(type.scored)}</td>
                  <td>
                    <div className="share">
                      <Bar value={type.recall ?? 0} max={1} />
                      <span className="num small muted">{share(type.recall)}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Labelled</th>
                <th>Predicted</th>
                <th>Result</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.source_file}>
                  <td>
                    <p className="cell-title">{row.source_file}</p>
                    <p className="cell-sub">
                      {row.top3.map((t) => `${label(t.label)} ${t.score.toFixed(2)}`).join(" · ")}
                    </p>
                  </td>
                  <td>{label(row.true)}</td>
                  <td>{label(row.predicted)}</td>
                  <td>
                    <Result row={row} />
                  </td>
                  <td className={row.low_confidence ? "" : "muted"}>{row.low_confidence ? "Low" : "OK"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {report.per_document.length > ROWS_SHOWN && (
          <button type="button" className="btn btn-ghost show-more" onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Show fewer" : `Show all ${fmt(report.per_document.length)} documents`}
          </button>
        )}
      </div>
    </section>
  );
}
