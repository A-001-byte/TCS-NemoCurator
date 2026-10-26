import { useState } from "react";
import {
  ArrowRight,
  Workflow,
} from "lucide-react";
import { STAGES, entityLabel } from "../stages";
import { Bar, SectionHeader } from "../components/common";
import { fmt, pct } from "../format";
import ReasonList from "../components/ReasonList";

const PURITY_METRICS = [
  ["chunks_with_devanagari", "Chunks with Hindi letterhead text"],
  ["chunks_with_page_marker", "Chunks with “Page n” markers"],
  ["pincode_spans", "PIN-code-shaped numbers"],
  ["duplicate_chunks", "Duplicate chunks"],
];

function StageDetail({ stage }) {
  const info = STAGES[stage.stage] || { title: stage.stage, detail: "", unit: "items" };
  const reasons = Object.entries(stage.reason_counts || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  // Redaction rewrites text instead of removing chunks, so show what it changed.
  const entities = stage.entity_type_counts
    ? Object.entries(stage.entity_type_counts).sort((a, b) => b[1] - a[1])
    : null;
  // Healing deletes page-furniture lines, not documents or chunks: show purity before/after.
  const purity = stage.before && stage.after ? PURITY_METRICS : null;
  const healed = stage.reason_counts || {};
  const figures = purity
    ? [
        ["Documents in / out", `${fmt(stage.docs_in)} / ${fmt(stage.docs_out)}`],
        ["Furniture lines deleted", fmt(healed.furniture_lines_removed)],
        ["Kerning splits repaired", fmt(healed.ocr_splits_repaired)],
        ["Documents dropped", fmt(stage.removed)],
      ]
    : entities
    ? [
        ["Chunks in / out", `${fmt(stage.docs_in)} / ${fmt(stage.docs_out)}`],
        ["Entities redacted", fmt(stage.pii_entities_redacted)],
        ["Chunks modified", fmt(stage.chunks_with_pii)],
        ["Documents with PII", fmt(stage.documents_with_pii)],
      ]
    : [
        ["In", fmt(stage.docs_in)],
        ["Out", fmt(stage.docs_out)],
        ["Removed", fmt(stage.removed)],
        ["Kept", pct(stage.docs_out, stage.docs_in)],
      ];

  return (
    <div className="card stage-detail">
      <div>
        <p className="label">Stage detail</p>
        <h3>{info.title}</h3>
        <p className="body">{info.detail}</p>

        <dl className="kv-row">
          {figures.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="stage-side">
        {purity ? (
          <>
            <p className="label">Corpus purity, before → after</p>
            <ul className="reason-list">
              {purity.map(([key, label]) => (
                <li key={key}>
                  <div className="reason-row">
                    <span>{label}</span>
                    <span className="num">
                      {fmt(stage.before[key])} <span className="muted">→</span> {fmt(stage.after[key])}
                    </span>
                  </div>
                  <Bar value={stage.after[key]} max={stage.before[key]} />
                </li>
              ))}
            </ul>
          </>
        ) : entities ? (
          <>
            <p className="label">Entities redacted by type</p>
            <ReasonList rows={entities} label={entityLabel} />
          </>
        ) : (
          <>
            <p className="label">Removal reasons</p>
            {reasons.length === 0 ? (
              <p className="muted small">
                Nothing is removed at this stage; every {info.unit.replace(/s$/, "")} passes through.
              </p>
            ) : (
              <ReasonList rows={reasons} />
            )}
          </>
        )}

        {stage.failures?.length > 0 && (
          <div className="failures">
            <p className="label">Files skipped</p>
            {stage.failures.map((f) => (
              <p key={f.file} className="mono small">
                {f.file} <span className="muted">({f.error})</span>
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Pipeline({ stages }) {
  const [selected, setSelected] = useState(stages[0]?.stage);
  const current = stages.find((s) => s.stage === selected) || stages[0];

  return (
    <section id="pipeline" className="section">
      <SectionHeader
        title="How the pipeline works"
        description={`${stages.length} stages run in a fixed order. Select a stage to see what it does and what it changed.`}
      />

      <div className="flow-canvas">
        <ol className="flow">
          {stages.map((stage, i) => {
            const info = STAGES[stage.stage] || { title: stage.stage, unit: "items" };
            const Icon = info.icon || Workflow;
            return (
              <li key={stage.stage} className="flow-step">
                <button
                  type="button"
                  className="flow-node"
                  aria-pressed={selected === stage.stage}
                  onClick={() => setSelected(stage.stage)}
                >
                  <span className="flow-top">
                    <span className="flow-icon">
                      <Icon size={16} />
                    </span>
                    <span className="flow-index">{String(i + 1).padStart(2, "0")}</span>
                  </span>
                  <span className="flow-title">{info.title}</span>
                  <span className="flow-count">
                    {fmt(stage.docs_in)} <ArrowRight size={12} /> {fmt(stage.docs_out)}
                  </span>
                  <span className="flow-foot">
                    <span className="muted">{info.unit}</span>
                    {stage.removed > 0 && (
                      <span className="badge badge-primary">−{fmt(stage.removed)}</span>
                    )}
                    {stage.pii_entities_redacted > 0 && (
                      <span className="badge badge-success">{fmt(stage.pii_entities_redacted)} redacted</span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>

      {current && <StageDetail stage={current} />}
    </section>
  );
}
