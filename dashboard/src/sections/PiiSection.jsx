import { useState } from "react";
import {
  CircleCheck,
} from "lucide-react";
import { ENTITIES, entityLabel } from "../stages";
import { Bar, SectionHeader } from "../components/common";
import { fmt } from "../format";
import { byStage } from "../summary";

const SUPPRESSED = "ACCOUNT_NUMBER_SUPPRESSED";

const EXAMPLES_SHOWN = 6;

function Snippet({ ex, redacted }) {
  const kept = ex.entity_type === SUPPRESSED;
  return (
    <p className="snippet">
      <span className="muted">…</span>
      {ex.context_before}
      {redacted && !kept ? (
        <span className="tag-redacted">[REDACTED_{ex.entity_type}]</span>
      ) : (
        <mark className={kept ? "mark-kept" : "mark-pii"}>{ex.before}</mark>
      )}
      {ex.context_after}
      <span className="muted">…</span>
    </p>
  );
}

export default function PiiSection({ summary }) {
  const pii = byStage(summary.stages, "pii_redact");
  const counts = Object.entries(summary.pii_entity_type_counts || {}).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...counts.map(([, v]) => v), 0);
  const exampleTypes = [...new Set(summary.pii_examples.map((e) => e.entity_type))];
  const [filter, setFilter] = useState("ALL");
  const [showAll, setShowAll] = useState(false);
  const matching = summary.pii_examples.filter((e) => filter === "ALL" || e.entity_type === filter);
  const examples = showAll ? matching : matching.slice(0, EXAMPLES_SHOWN);

  const checks = [
    {
      label: "Account-shaped numbers kept as phone or fax",
      value: pii.account_numbers_suppressed,
      note: "The surrounding words were Fax or Tel, so they were not treated as bank accounts.",
    },
    {
      label: "SWIFT-shaped words left untouched",
      value: pii.swift_candidates_rejected_no_cue,
      note: "Uppercase words such as ANNEXURE fit the pattern but had no SWIFT/BIC label nearby.",
    },
    {
      label: "Chunks flagged for human review",
      value: pii.chunks_needing_review,
      note: "Matches where context pointed neither way.",
    },
  ];

  return (
    <section id="pii" className="section">
      <SectionHeader
        title="PII redaction"
        description={`${fmt(summary.pii_entities_redacted)} identifiers replaced with typed placeholders in ${fmt(pii.chunks_with_pii)} of ${fmt(pii.docs_in)} chunks. Redaction runs after deduplication so content hashes stay stable.`}
      />

      <div className="grid-2">
        <article className="card">
          <h3>Entities redacted by type</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Entity</th>
                <th className="right">Count</th>
                <th className="w-bar">Share</th>
              </tr>
            </thead>
            <tbody>
              {counts.map(([type, count]) => (
                <tr key={type}>
                  <td>
                    <p className="cell-title">{entityLabel(type)}</p>
                    <p className="cell-sub">{ENTITIES[type]?.note}</p>
                  </td>
                  <td className="right num">{fmt(count)}</td>
                  <td>
                    <Bar value={count} max={maxCount} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>

        <article className="card">
          <h3>Context validation</h3>
          <p className="body">
            A pattern match alone is not enough. Ambiguous matches are checked against the words
            around them, trading a little recall for precision so real regulatory text is not
            destroyed.
          </p>
          <ul className="check-list">
            {checks.map((c) => (
              <li key={c.label}>
                <CircleCheck size={18} className="check-icon" />
                <div>
                  <p className="cell-title">
                    {c.label}
                    <span className="check-value num">{fmt(c.value)}</span>
                  </p>
                  <p className="cell-sub">{c.note}</p>
                </div>
              </li>
            ))}
          </ul>
        </article>
      </div>

      <article className="card">
        <div className="card-head">
          <div>
            <h3>Before and after</h3>
            <p className="cell-sub">
              Real spans from the source PDFs · showing {fmt(examples.length)} of{" "}
              {fmt(matching.length)} {filter === "ALL" ? "recorded" : "matching"} examples
            </p>
          </div>
        </div>

        <div className="segmented" role="tablist" aria-label="Filter examples by entity type">
          {["ALL", ...exampleTypes].map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={filter === t}
              onClick={() => {
                setFilter(t);
                setShowAll(false);
              }}
            >
              {t === "ALL" ? "All" : entityLabel(t)}
            </button>
          ))}
        </div>

        <ul className="example-list">
          {examples.map((ex, i) => (
            <li key={`${ex.doc_id}-${i}`} className="example">
              <div className="example-meta">
                <span className={`badge ${ex.entity_type === SUPPRESSED ? "badge-info" : "badge-primary"}`}>
                  {entityLabel(ex.entity_type)}
                </span>
                <span className="mono cell-sub">{ex.doc_id}</span>
              </div>
              <div className="example-pair">
                <div>
                  <p className="label">Original</p>
                  <Snippet ex={ex} />
                </div>
                <div>
                  <p className="label">{ex.entity_type === SUPPRESSED ? "Output (kept)" : "Output"}</p>
                  <Snippet ex={ex} redacted />
                </div>
              </div>
            </li>
          ))}
        </ul>

        {matching.length > EXAMPLES_SHOWN && (
          <button type="button" className="btn btn-secondary show-more" onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Show fewer" : `Show all ${fmt(matching.length)} examples`}
          </button>
        )}
      </article>
    </section>
  );
}
