import { useMemo, useState } from "react";
import { Bar, SectionHeader } from "../components/common";
import { fmt, pct } from "../format";

const ROWS_SHOWN = 10;

export default function Tokens({ report }) {
  const [showAll, setShowAll] = useState(false);
  const documents = useMemo(() => [...report.per_document].sort((a, b) => b.tokens - a.tokens), [report]);
  const chunks = documents.reduce((sum, d) => sum + d.chunks, 0);
  const largest = documents[0]?.tokens ?? 0;
  // The counting method is named in the file; word counts are labelled as words, never as tokens.
  const unit = /word/i.test(report.tokenizer) ? "words" : "tokens";
  const unitTitle = unit[0].toUpperCase() + unit.slice(1);
  const rows = showAll ? documents : documents.slice(0, ROWS_SHOWN);

  const metrics = [
    { label: `Total ${unit}`, value: fmt(report.total_tokens), note: `Counted with ${report.tokenizer}` },
    { label: "Documents", value: fmt(documents.length), note: `${fmt(chunks)} curated chunks` },
    {
      label: `${unitTitle} per chunk`,
      value: chunks ? fmt(Math.round(report.total_tokens / chunks)) : "–",
      note: "Average over the whole corpus",
    },
  ];

  return (
    <section id="tokens" className="section">
      <SectionHeader
        title="Token statistics"
        description={`How much training text the curated corpus holds, per document, counted in ${unit}.`}
      />

      <div className="metric-grid">
        {metrics.map((m) => (
          <article className="card metric" key={m.label}>
            <p className="metric-label">{m.label}</p>
            <p className="metric-value">{m.value}</p>
            <p className="metric-note">{m.note}</p>
          </article>
        ))}
      </div>

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Document</th>
                <th className="right">Chunks</th>
                <th className="right">{unitTitle}</th>
                <th className="w-bar">Share of corpus</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.source_file}>
                  <td className="cell-title">{d.source_file}</td>
                  <td className="right num">{fmt(d.chunks)}</td>
                  <td className="right num">{fmt(d.tokens)}</td>
                  <td>
                    <div className="share">
                      <Bar value={d.tokens} max={largest} />
                      <span className="num small muted">{pct(d.tokens, report.total_tokens)}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {documents.length > ROWS_SHOWN && (
          <button type="button" className="btn btn-ghost show-more" onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Show fewer" : `Show all ${fmt(documents.length)} documents`}
          </button>
        )}
      </div>
    </section>
  );
}
