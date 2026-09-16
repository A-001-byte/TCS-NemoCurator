import { useEffect, useState } from "react";
import "./App.css";

const STAGE_LABELS = {
  extract: "PDF Extraction",
  clean_langid: "Clean + Language ID",
  dedup: "Deduplication",
  quality_filter: "Quality Filter",
  pii_redact: "PII Redaction",
  output: "JSONL Output",
};

function StageFunnel({ stages }) {
  return (
    <div className="funnel">
      {stages.map((stage) => (
        <div className="funnel-stage" key={stage.stage}>
          <div className="funnel-stage-header">
            <span className="funnel-stage-name">
              {STAGE_LABELS[stage.stage] || stage.stage}
            </span>
            <span className="funnel-stage-counts">
              {stage.docs_in} → {stage.docs_out}
            </span>
          </div>
          <div className="funnel-bar-track">
            <div
              className="funnel-bar-fill"
              style={{
                width: `${stage.docs_in ? (stage.docs_out / stage.docs_in) * 100 : 0}%`,
              }}
            />
          </div>
          {stage.removed > 0 && (
            <div className="funnel-removed">
              −{stage.removed} removed
              {Object.keys(stage.reason_counts || {}).length > 0 && (
                <span className="funnel-reasons">
                  {" "}
                  ({Object.entries(stage.reason_counts)
                    .filter(([, v]) => v > 0)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(", ")})
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function PiiPanel({ examples, entityCounts, nameDetectionAvailable }) {
  return (
    <div className="panel">
      <h2>PII Redaction — Before / After</h2>
      <p className="panel-sub">
        Real text extracted from actual RBI/bank KYC documents, redaction applied by the pipeline.
        {!nameDetectionAvailable && (
          <strong> Person-name detection (spaCy NER) was unavailable at run time — name entities are not included below.</strong>
        )}
      </p>
      <div className="entity-chips">
        {Object.entries(entityCounts || {}).map(([type, count]) => (
          <span className="chip" key={type}>
            {type}: {count}
          </span>
        ))}
      </div>
      <div className="examples-list">
        {examples.slice(0, 8).map((ex, i) => (
          <div className="example-card" key={i}>
            <div className="example-type">{ex.entity_type}</div>
            <div className="example-before">
              <span className="label">before:</span>{" "}
              {ex.context_before}
              <mark>{ex.before}</mark>
              {ex.context_after}
            </div>
            <div className="example-after">
              <span className="label">after:</span>{" "}
              {ex.context_before}
              <span className="redacted-tag">[REDACTED_{ex.entity_type}]</span>
              {ex.context_after}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CorpusSummary({ summary }) {
  const extractStage = summary.stages.find((s) => s.stage === "extract");
  const outputStage = summary.stages.find((s) => s.stage === "output");
  return (
    <div className="stat-row">
      <div className="stat-card">
        <div className="stat-value">{extractStage?.docs_in ?? "-"}</div>
        <div className="stat-label">PDFs Ingested</div>
      </div>
      <div className="stat-card">
        <div className="stat-value">{summary.duplicates_removed}</div>
        <div className="stat-label">Duplicate Chunks Removed</div>
      </div>
      <div className="stat-card">
        <div className="stat-value">{summary.pii_entities_redacted}</div>
        <div className="stat-label">PII Entities Redacted</div>
      </div>
      <div className="stat-card">
        <div className="stat-value">{outputStage?.docs_out ?? "-"}</div>
        <div className="stat-label">Final Curated Chunks</div>
      </div>
      <div className="stat-card">
        <div className="stat-value">
          {summary.final_output_chars ? summary.final_output_chars.toLocaleString() : "-"}
        </div>
        <div className="stat-label">Total Characters Curated</div>
      </div>
    </div>
  );
}

function DocumentDrilldown({ documents }) {
  const [selectedId, setSelectedId] = useState(null);
  const selected = documents.find((d) => d.doc_id === selectedId) || null;

  return (
    <div className="panel">
      <h2>Document Drill-down</h2>
      <p className="panel-sub">Click a source document to see its journey through the pipeline.</p>
      <div className="doc-drilldown">
        <ul className="doc-list">
          {documents.map((doc) => (
            <li key={doc.doc_id}>
              <button
                className={`doc-list-item ${selectedId === doc.doc_id ? "active" : ""}`}
                onClick={() => setSelectedId(doc.doc_id)}
              >
                {doc.source_file}
              </button>
            </li>
          ))}
        </ul>
        <div className="doc-detail">
          {selected ? (
            <>
              <h3>{selected.source_file}</h3>
              <div className="doc-detail-row">
                <span>Characters extracted</span>
                <span>{selected.char_count.toLocaleString()}</span>
              </div>
              <div className="doc-detail-row">
                <span>Chunks surviving dedup</span>
                <span>{selected.chunks_after_dedup}</span>
              </div>
              <div className="doc-detail-row">
                <span>Chunks surviving quality filter</span>
                <span>{selected.chunks_after_quality_filter}</span>
              </div>
              <div className="doc-detail-row">
                <span>Chunks with PII redacted</span>
                <span>{selected.chunks_with_pii_redacted}</span>
              </div>
            </>
          ) : (
            <p className="doc-detail-empty">Select a document to see details.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/pipeline_summary.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(setSummary)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>NeMo-Curator-Equivalent Pipeline — BFSI/KYC Corpus</h1>
        <p className="app-subtitle">
          Real RBI &amp; bank KYC/AML PDFs → cleaned, deduplicated, PII-redacted,
          fine-tuning-ready JSONL.
        </p>
        <p className="honesty-banner">
          Extraction, cleaning, language ID, dedup, quality filtering and PII redaction
          below are <strong>equivalent-logic stages</strong> (NeMo Curator's own
          <code>ProcessingStage</code>/<code>Pipeline</code> API failed to install on this
          machine — see README). Person-name PII uses spaCy NER; NVIDIA's shipped path uses
          GLiNER-PII. No fine-tuning was performed.
        </p>
      </header>

      {error && (
        <div className="error-banner">
          Could not load pipeline_summary.json ({error}). Run{" "}
          <code>python -m pipeline.run</code> from the project root first.
        </div>
      )}

      {summary && (
        <main>
          <CorpusSummary summary={summary} />
          <div className="panel">
            <h2>Pipeline Funnel</h2>
            <StageFunnel stages={summary.stages} />
          </div>
          <PiiPanel
            examples={summary.pii_examples}
            entityCounts={summary.pii_entity_type_counts}
            nameDetectionAvailable={summary.name_detection_available}
          />
          <DocumentDrilldown documents={summary.documents || []} />
        </main>
      )}
    </div>
  );
}
