import {
  Info,
  TriangleAlert,
} from "lucide-react";
import { fmt, pct } from "../format";
import { byStage } from "../summary";

export default function Overview({ summary }) {
  const extract = byStage(summary.stages, "extract");
  const dedup = byStage(summary.stages, "dedup");
  const pii = byStage(summary.stages, "pii_redact");
  const skipped = extract.docs_in - extract.docs_out;

  const metrics = [
    {
      label: "Source PDFs",
      value: fmt(extract.docs_in),
      note: `${fmt(extract.docs_out)} extracted${skipped ? ` · ${skipped} skipped (no text layer)` : ""}`,
    },
    {
      label: "Curated chunks",
      value: fmt(summary.final_output_chunks),
      note: `${fmt(summary.final_output_chars)} characters · ${pct(summary.final_output_chunks, dedup.docs_in)} of chunks kept`,
    },
    {
      label: "Duplicates removed",
      value: fmt(summary.duplicates_removed),
      note: `${fmt(summary.cross_doc_boilerplate_removed)} were boilerplate shared across banks`,
    },
    {
      label: "PII entities redacted",
      value: fmt(summary.pii_entities_redacted),
      note: `in ${fmt(pii.chunks_with_pii)} chunks across ${fmt(pii.documents_with_pii)} documents`,
    },
  ];

  return (
    <section id="overview" className="section">
      <div className="hero">
        <p className="eyebrow">BFSI · KYC / AML</p>
        <h1>Regulatory corpus curation</h1>
        <p className="lead">
          {fmt(extract.docs_in)} public RBI, FIU-IND and bank KYC/AML documents turned into{" "}
          {fmt(summary.final_output_chunks)} clean, deduplicated, PII-redacted chunks ready for
          language-model fine-tuning.
        </p>
      </div>

      <div className="metric-grid">
        {metrics.map((m) => (
          <article className="card metric" key={m.label}>
            <p className="metric-label">{m.label}</p>
            <p className="metric-value">{m.value}</p>
            <p className="metric-note">{m.note}</p>
          </article>
        ))}
      </div>

      <div className="callout">
        <Info size={18} />
        <p>
          Each stage is a NeMo Curator–equivalent Python module that follows Curator's stage
          order and filter semantics. Person names are found with{" "}
          {summary.name_detection_available
            ? "spaCy NER"
            : "no NER model (unavailable in this run)"}
          ; NVIDIA's reference path uses GLiNER-PII. No model was fine-tuned in this run.
        </p>
      </div>

      {summary.name_detection_available === false && (
        <div className="card empty" role="alert">
          <TriangleAlert size={18} />
          <p>
            <strong>Person-name detection is off in this run</strong>, so names are not redacted and the
            PII count is lower than with the model loaded.
            {summary.name_detection_error ? ` Reason: ${summary.name_detection_error}.` : ""} Install the
            spaCy model with <code>python -m spacy download en_core_web_sm</code> and run again.
          </p>
        </div>
      )}
    </section>
  );
}
