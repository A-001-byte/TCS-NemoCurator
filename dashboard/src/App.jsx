import { useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard,
  Workflow,
  Library,
  ShieldCheck,
  Files,
  Search,
  Moon,
  Sun,
  ChevronRight,
  ArrowRight,
  Info,
  CircleCheck,
  TriangleAlert,
  Database,
  Boxes,
  Upload,
  FileText,
  X,
  Play,
  Download,
  LoaderCircle,
  Scale,
} from "lucide-react";
import { STAGES, ENTITIES, reasonLabel, entityLabel } from "./stages";
import {
  prepareCorpus,
  rankMatches,
  classify,
  CANDIDATE_LIMIT,
  HIGH_SIMILARITY,
  MODERATE_SIMILARITY,
} from "./similarity";
import "./App.css";

const SECTIONS = [
  { id: "overview", title: "Overview", icon: LayoutDashboard },
  { id: "pipeline", title: "Pipeline", icon: Workflow },
  { id: "corpus", title: "Corpus quality", icon: Library },
  { id: "nemo", title: "NeMo comparison", icon: Scale },
  { id: "pii", title: "PII redaction", icon: ShieldCheck },
  { id: "documents", title: "Source documents", icon: Files },
  { id: "search", title: "Similarity search", icon: Search },
  { id: "run", title: "Process documents", icon: Upload },
];

const EXAMPLE_QUERY =
  "The customer submitted KYC documents including PAN details, address proof and bank account information. The transaction history shows multiple unusual transfers requiring further review.";
const EXCERPT_CHARS = 480;
const SUPPRESSED = "ACCOUNT_NUMBER_SUPPRESSED";
const EXAMPLES_SHOWN = 6;

const fmt = (n) => (typeof n === "number" ? n.toLocaleString("en-US") : "–");
const pct = (part, whole) => (whole ? `${((part / whole) * 100).toFixed(1)}%` : "–");
const byStage = (stages, name) => stages.find((s) => s.stage === name) || {};

/* ---------- shell ---------- */

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem("theme");
      if (saved) return saved;
    } catch {
      /* storage unavailable: fall back to system preference */
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* non-essential */
    }
  }, [theme]);

  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

function useActiveSection(ready) {
  const [active, setActive] = useState(SECTIONS[0].id);
  useEffect(() => {
    if (!ready) return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.find((e) => e.isIntersecting);
        if (visible) setActive(visible.target.id);
      },
      { rootMargin: "-30% 0px -60% 0px" }
    );
    SECTIONS.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [ready]);
  return active;
}

function Sidebar({ active, theme, onToggleTheme, documentCount }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">
          <Boxes size={18} />
        </span>
        <div>
          <p className="brand-name">KYC Curator</p>
          <p className="brand-sub">BFSI corpus pipeline</p>
        </div>
      </div>

      <nav className="nav" aria-label="Sections">
        {SECTIONS.map(({ id, title, icon: Icon }) => (
          <a
            key={id}
            href={`#${id}`}
            className="nav-item"
            aria-current={active === id ? "true" : undefined}
          >
            <Icon size={18} />
            <span>{title}</span>
          </a>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="source-note">
          <Database size={14} />
          <span>{fmt(documentCount)} source documents</span>
        </div>
        <button type="button" className="btn btn-ghost btn-block" onClick={onToggleTheme}>
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
      </div>
    </aside>
  );
}

function Topbar({ active }) {
  const section = SECTIONS.find((s) => s.id === active);
  return (
    <header className="topbar">
      <div className="crumbs">
        <span className="muted">Curation run</span>
        <ChevronRight size={16} className="muted" />
        <span>{section?.title}</span>
      </div>
      <span className="pill">
        <span className="dot" />
        Snapshot: pipeline_summary.json
      </span>
    </header>
  );
}

function SectionHeader({ title, description }) {
  return (
    <div className="section-head">
      <h2>{title}</h2>
      {description && <p className="section-desc">{description}</p>}
    </div>
  );
}

function Bar({ value, max, tone = "primary" }) {
  const width = max ? Math.max((value / max) * 100, value > 0 ? 2 : 0) : 0;
  return (
    <div className="bar">
      <div className={`bar-fill fill-${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

/* ---------- overview ---------- */

function Overview({ summary }) {
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
    </section>
  );
}

/* ---------- pipeline ---------- */

function ReasonList({ rows, total }) {
  const max = total ?? Math.max(...rows.map(([, v]) => v), 0);
  return (
    <ul className="reason-list">
      {rows.map(([key, count]) => (
        <li key={key}>
          <div className="reason-row">
            <span>{reasonLabel(key)}</span>
            <span className="num">
              {fmt(count)}
              {total ? <span className="muted"> · {pct(count, total)}</span> : null}
            </span>
          </div>
          <Bar value={count} max={max} />
        </li>
      ))}
    </ul>
  );
}

function StageDetail({ stage }) {
  const info = STAGES[stage.stage] || { title: stage.stage, detail: "", unit: "items" };
  const reasons = Object.entries(stage.reason_counts || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);

  return (
    <div className="card stage-detail">
      <div>
        <p className="label">Stage detail</p>
        <h3>{info.title}</h3>
        <p className="body">{info.detail}</p>

        <dl className="kv-row">
          {[
            ["In", fmt(stage.docs_in)],
            ["Out", fmt(stage.docs_out)],
            ["Removed", fmt(stage.removed)],
            ["Kept", pct(stage.docs_out, stage.docs_in)],
          ].map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="stage-side">
        <p className="label">Removal reasons</p>
        {reasons.length === 0 ? (
          <p className="muted small">Nothing is removed at this stage; every {info.unit} passes through.</p>
        ) : (
          <ReasonList rows={reasons} />
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

function Pipeline({ stages }) {
  const [selected, setSelected] = useState(stages[0]?.stage);
  const current = stages.find((s) => s.stage === selected) || stages[0];

  return (
    <section id="pipeline" className="section">
      <SectionHeader
        title="How the pipeline works"
        description="Six stages run in a fixed order. Select a stage to see what it does and what it removed."
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

/* ---------- corpus quality ---------- */

function CorpusQuality({ summary }) {
  const quality = byStage(summary.stages, "quality_filter");
  const dedup = byStage(summary.stages, "dedup");
  const tagged = summary.regulatory_tagged_count;
  const untagged = summary.regulatory_untagged_count;
  const total = tagged + untagged;
  const dupRows = Object.entries(dedup.reason_counts || {}).sort((a, b) => b[1] - a[1]);
  const qualityRows = Object.entries(quality.reason_counts || {}).sort((a, b) => b[1] - a[1]);

  return (
    <section id="corpus" className="section">
      <SectionHeader
        title="Corpus quality"
        description="What the curated corpus contains, and why text was removed on the way."
      />

      <div className="grid-3">
        <article className="card">
          <h3>Regulatory coverage</h3>
          <p className="body">
            Every surviving chunk is scanned for BFSI regulatory terms such as KYC, AML, CDD, PEP
            and STR. Tagging never removes text; it marks which chunks carry regulatory content.
          </p>
          <div className="stack-bar" role="img" aria-label={`${pct(tagged, total)} of chunks tagged`}>
            <div className="fill-primary" style={{ width: pct(tagged, total) }} />
          </div>
          <dl className="kv-list">
            <div>
              <dt>
                <span className="swatch fill-primary" /> Contain regulatory terms
              </dt>
              <dd>
                {fmt(tagged)} <span className="muted">· {pct(tagged, total)}</span>
              </dd>
            </div>
            <div>
              <dt>
                <span className="swatch swatch-rest" /> No regulatory terms
              </dt>
              <dd>
                {fmt(untagged)} <span className="muted">· {pct(untagged, total)}</span>
              </dd>
            </div>
            <div>
              <dt>High regulatory density</dt>
              <dd>
                {fmt(summary.high_density_count)}{" "}
                <span className="muted">· {pct(summary.high_density_count, total)}</span>
              </dd>
            </div>
          </dl>
        </article>

        <article className="card">
          <h3>Duplicates removed</h3>
          <p className="body">
            Indian bank policies copy large parts of the RBI Master Direction. Keeping one copy of
            each shared clause stops the model over-weighting it.
          </p>
          <ReasonList rows={dupRows} total={dedup.removed} />
        </article>

        <article className="card">
          <h3>Low-quality chunks removed</h3>
          <p className="body">
            Chunks dominated by tables of numbers, stray symbols or repeated words teach a model
            nothing about regulation, so they are dropped after deduplication.
          </p>
          <ReasonList rows={qualityRows} total={quality.removed} />
        </article>
      </div>
    </section>
  );
}

/* ---------- NeMo Curator comparison ---------- */

function NemoComparison() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/nemo_comparison.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(setReport)
      .catch((err) => setError(err.message));
  }, []);

  if (!report) {
    return (
      <section id="nemo" className="section">
        <SectionHeader title="Checked against NVIDIA NeMo Curator" />
        <div className="card empty">
          {error ? <TriangleAlert size={18} /> : <LoaderCircle size={18} className="spin" />}
          <p>
            {error
              ? `No comparison snapshot found (${error}). Generate it with python -m pipeline.nemo_compare on a machine with NeMo Curator installed.`
              : "Loading comparison…"}
          </p>
        </div>
      </section>
    );
  }

  const { nemo, ours, overlap, input_chunks: total } = report;
  const docs = [...new Set([...Object.keys(report.nemo_removed_by_doc), ...Object.keys(report.ours_removed_by_doc)])]
    .map((doc) => ({
      doc,
      nemo: report.nemo_removed_by_doc[doc] || 0,
      ours: report.ours_removed_by_doc[doc] || 0,
    }))
    .sort((a, b) => b.nemo + b.ours - (a.nemo + a.ours));
  const filters = [...report.filters].sort((a, b) => b.removed - a.removed);
  const maxFilter = Math.max(...filters.map((f) => f.removed), 0);

  const sides = [
    { title: "Our quality filter", data: ours, tone: "primary", note: "Custom BFSI thresholds (pipeline/quality.py)" },
    { title: `NeMo Curator ${report.nemo_curator_version.split("+")[0]}`, data: nemo, tone: "info", note: `${filters.length} heuristic filters at NVIDIA defaults` },
  ];

  return (
    <section id="nemo" className="section">
      <SectionHeader
        title="Checked against NVIDIA NeMo Curator"
        description={`The same ${fmt(total)} deduplicated chunks our quality filter receives were run through NVIDIA NeMo Curator's own heuristic filters, using its Pipeline and ${report.executor} executor on an Ubuntu VM (${report.pipeline_seconds} s). NeMo's default thresholds come from the Gopher rules for web text; they were not tuned for regulatory PDFs.`}
      />

      <div className="grid-3">
        {sides.map((s) => (
          <article className="card metric" key={s.title}>
            <p className="metric-label">{s.title}</p>
            <p className="metric-value">
              {fmt(s.data.removed)} <span className="metric-unit">removed</span>
            </p>
            <div className="bar">
              <div className={`bar-fill fill-${s.tone}`} style={{ width: pct(s.data.removed, total) }} />
            </div>
            <p className="metric-note">
              {fmt(s.data.kept)} of {fmt(total)} kept ({pct(s.data.kept, total)}) · {s.note}
            </p>
          </article>
        ))}

        <article className="card metric">
          <p className="metric-label">Where the two agree</p>
          <dl className="kv-list">
            <div>
              <dt>
                <span className="swatch fill-success" /> Removed by both
              </dt>
              <dd>{fmt(overlap.removed_by_both)}</dd>
            </div>
            <div>
              <dt>
                <span className="swatch fill-info" /> Only NeMo
              </dt>
              <dd>{fmt(overlap.only_nemo)}</dd>
            </div>
            <div>
              <dt>
                <span className="swatch fill-primary" /> Only ours
              </dt>
              <dd>{fmt(overlap.only_ours)}</dd>
            </div>
          </dl>
        </article>
      </div>

      <div className="grid-wide">
        <article className="card">
          <h3>NeMo filters, one at a time</h3>
          <table className="table">
            <thead>
              <tr>
                <th>NeMo filter</th>
                <th className="right">Removed</th>
                <th className="right">Also ours</th>
                <th className="w-bar" />
              </tr>
            </thead>
            <tbody>
              {filters.map((f) => (
                <tr key={f.key}>
                  <td>
                    <p className="cell-title">{f.label}</p>
                    <p className="cell-sub">
                      {f.comparable_to ? `Our equivalent: ${reasonLabel(f.comparable_to).toLowerCase()}` : "No equivalent in our filter"}
                    </p>
                  </td>
                  <td className={`right num ${f.removed ? "" : "muted"}`}>{fmt(f.removed)}</td>
                  <td className={`right num ${f.also_removed_by_ours ? "" : "muted"}`}>{fmt(f.also_removed_by_ours)}</td>
                  <td>
                    <Bar value={f.removed} max={maxFilter} tone="info" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="cell-sub">
            A chunk can fail several filters, so these counts add up to more than NeMo's total.
          </p>
        </article>

        <article className="card">
          <h3>Removed chunks by document</h3>
          <table className="table table-wrap">
            <thead>
              <tr>
                <th>Document</th>
                <th className="right">NeMo</th>
                <th className="right">Ours</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.doc}>
                  <td className="cell-title">{d.doc}</td>
                  <td className={`right num ${d.nemo ? "" : "muted"}`}>{fmt(d.nemo)}</td>
                  <td className={`right num ${d.ours ? "" : "muted"}`}>{fmt(d.ours)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      </div>
    </section>
  );
}

/* ---------- PII ---------- */

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

function PiiSection({ summary }) {
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

/* ---------- documents ---------- */

const DOC_COLUMNS = [
  { key: "source_file", label: "Document" },
  { key: "char_count", label: "Characters", numeric: true },
  { key: "chunks_after_dedup", label: "After dedup", numeric: true },
  { key: "chunks_after_quality_filter", label: "After quality filter", numeric: true },
  { key: "chunks_with_pii_redacted", label: "Chunks with PII", numeric: true },
];

function Documents({ documents }) {
  const [sort, setSort] = useState({ key: "chunks_after_quality_filter", dir: -1 });
  const rows = useMemo(
    () =>
      [...documents].sort((a, b) => {
        const x = a[sort.key];
        const y = b[sort.key];
        return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * sort.dir;
      }),
    [documents, sort]
  );
  const totalChunks = documents.reduce((s, d) => s + d.chunks_after_quality_filter, 0);
  const largest = Math.max(...documents.map((d) => d.chunks_after_quality_filter), 0);
  const toggle = (key) =>
    setSort((s) => ({ key, dir: s.key === key ? -s.dir : key === "source_file" ? 1 : -1 }));

  return (
    <section id="documents" className="section">
      <SectionHeader
        title="Source documents"
        description="Every PDF that produced text, with how many of its chunks survived each stage. Select a column heading to sort."
      />

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                {DOC_COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    className={c.numeric ? "right" : ""}
                    aria-sort={sort.key === c.key ? (sort.dir > 0 ? "ascending" : "descending") : "none"}
                  >
                    <button type="button" className="th-btn" onClick={() => toggle(c.key)}>
                      {c.label}
                      <span className="sort-ind">{sort.key === c.key ? (sort.dir > 0 ? "↑" : "↓") : ""}</span>
                    </button>
                  </th>
                ))}
                <th className="w-bar">Share of corpus</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => {
                const dropped = d.chunks_after_dedup - d.chunks_after_quality_filter;
                return (
                  <tr key={d.doc_id}>
                    <td>
                      <p className="cell-title">{d.source_file}</p>
                      {dropped > 0 && (
                        <p className="cell-sub">{fmt(dropped)} chunks dropped by the quality filter</p>
                      )}
                    </td>
                    <td className="right num">{fmt(d.char_count)}</td>
                    <td className="right num">{fmt(d.chunks_after_dedup)}</td>
                    <td className="right num">{fmt(d.chunks_after_quality_filter)}</td>
                    <td className={`right num ${d.chunks_with_pii_redacted ? "" : "muted"}`}>
                      {fmt(d.chunks_with_pii_redacted)}
                    </td>
                    <td>
                      <div className="share">
                        <Bar value={d.chunks_after_quality_filter} max={largest} />
                        <span className="num small muted">{pct(d.chunks_after_quality_filter, totalChunks)}</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

/* ---------- similarity search ---------- */

function parseCorpus(text) {
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter((item) => item && item.text?.trim())
    .map((item) => ({
      text: item.text,
      source_file: item.metadata?.source_file || "Unknown document",
      chunk_id: item.metadata?.chunk_id || "",
      keywords: item.metadata?.regulatory_keywords_found || [],
    }));
}

function scoreTone(score) {
  if (score >= HIGH_SIMILARITY) return "success";
  if (score >= MODERATE_SIMILARITY) return "primary";
  return "info";
}

function MatchResult({ result, corpusSize }) {
  const [best, ...others] = result.matches;
  if (!best) {
    return (
      <div className="card empty">
        <TriangleAlert size={18} />
        <p>No passage in the corpus shares vocabulary with this text.</p>
      </div>
    );
  }
  const text = best.document.text;

  return (
    <div className="grid-result">
      <article className="card">
        <div className="card-head">
          <div className="min-0">
            <p className="label">Closest passage</p>
            <h3 className="truncate">{best.document.source_file}</h3>
            <p className="cell-sub mono">{best.document.chunk_id}</p>
          </div>
          <div className="score">
            <p className="score-value num">{best.score.toFixed(3)}</p>
            <span className={`badge badge-${scoreTone(best.score)}`}>{classify(best.score)}</span>
          </div>
        </div>

        <blockquote className="excerpt">
          {text.length > EXCERPT_CHARS ? `${text.slice(0, EXCERPT_CHARS)}…` : text}
        </blockquote>

        {best.document.keywords.length > 0 && (
          <div className="keywords">
            <span className="label">Regulatory terms in this passage</span>
            <div className="chips">
              {best.document.keywords.map((k) => (
                <span key={k} className="chip">
                  {k}
                </span>
              ))}
            </div>
          </div>
        )}

        <p className="muted small">
          Scored {fmt(result.candidatesScored)} candidate chunks out of {fmt(corpusSize)}.
        </p>
      </article>

      <article className="card">
        <h3>Runners-up</h3>
        {others.length === 0 ? (
          <p className="muted small">No other passage scored above zero.</p>
        ) : (
          <ul className="reason-list">
            {others.map((m) => (
              <li key={m.document.chunk_id}>
                <div className="reason-row">
                  <span className="truncate">{m.document.source_file}</span>
                  <span className="num">{m.score.toFixed(3)}</span>
                </div>
                <Bar value={m.score} max={1} tone={scoreTone(m.score)} />
                <p className="cell-sub mono">{m.document.chunk_id}</p>
              </li>
            ))}
          </ul>
        )}
      </article>
    </div>
  );
}

function SimilaritySearch() {
  const [corpus, setCorpus] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState(EXAMPLE_QUERY);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/curated.jsonl", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => setCorpus(prepareCorpus(parseCorpus(text))))
      .catch((err) => setError(err.message));
  }, []);

  function run() {
    if (!corpus || !query.trim()) return;
    setBusy(true);
    // let the button repaint before the synchronous scoring pass
    setTimeout(() => {
      setResult(rankMatches(query, corpus));
      setBusy(false);
    }, 30);
  }

  const size = corpus?.totalDocuments;

  return (
    <section id="search" className="section">
      <SectionHeader
        title="Similarity search"
        description="Paste a clause or an excerpt from a new KYC document to find the closest passage in the curated corpus."
      />

      <div className="grid-search">
        <article className="card">
          <label htmlFor="query" className="label">
            Text to compare
          </label>
          <textarea
            id="query"
            className="textarea"
            rows={7}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={run}
              disabled={busy || !corpus || !query.trim()}
            >
              <Search size={16} />
              {busy ? "Searching…" : corpus ? "Find similar passages" : "Loading corpus…"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setQuery("");
                setResult(null);
              }}
              disabled={busy || !query}
            >
              Clear
            </button>
          </div>
          {error && <p className="error-text">Could not load curated.jsonl ({error}).</p>}
        </article>

        <article className="card">
          <h3>How matching works</h3>
          <ol className="steps">
            <li>
              The {size ? fmt(size) : "…"} curated chunks are indexed once as TF-IDF vectors when the
              page loads.
            </li>
            <li>
              Your text is compared by word overlap, and the top {CANDIDATE_LIMIT} candidates are
              scored with cosine similarity.
            </li>
            <li>
              A score of {HIGH_SIMILARITY} or more is high similarity, {MODERATE_SIMILARITY} or more is
              moderate, and anything lower is low.
            </li>
          </ol>
        </article>
      </div>

      {result && <MatchResult result={result} corpusSize={size} />}
    </section>
  );
}

/* ---------- run on new documents ---------- */

const API_HINT = "Start it with: venv/Scripts/python -m pipeline.server";

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

function download(filename, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const fileSize = (bytes) =>
  bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;

function RunResult({ result }) {
  const { summary, curated_jsonl: curated } = result;
  const stem = new Date().toISOString().slice(0, 19).replaceAll(":", "-");
  const firstRow = curated.split("\n").find((line) => line.trim());

  return (
    <div className="grid-result">
      <article className="card">
        <div className="card-head">
          <div>
            <p className="label">Run complete</p>
            <h3>
              {fmt(summary.final_output_chunks)} curated chunks from {fmt(summary.stages[0]?.docs_in)}{" "}
              {summary.stages[0]?.docs_in === 1 ? "document" : "documents"}
            </h3>
          </div>
          <span className="badge badge-success">
            <CircleCheck size={14} /> Done
          </span>
        </div>

        <table className="table">
          <thead>
            <tr>
              <th>Stage</th>
              <th className="right">In</th>
              <th className="right">Out</th>
              <th>Removed</th>
            </tr>
          </thead>
          <tbody>
            {summary.stages.map((s) => (
              <tr key={s.stage}>
                <td className="cell-title">{STAGES[s.stage]?.title || s.stage}</td>
                <td className="right num">{fmt(s.docs_in)}</td>
                <td className="right num">{fmt(s.docs_out)}</td>
                <td className="cell-sub">
                  {Object.entries(s.reason_counts || {})
                    .filter(([, v]) => v > 0)
                    .map(([k, v]) => `${reasonLabel(k)}: ${fmt(v)}`)
                    .join(" · ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {firstRow && (
          <div>
            <p className="label">First output record</p>
            <pre className="code-block">{JSON.stringify(JSON.parse(firstRow), null, 2)}</pre>
          </div>
        )}
      </article>

      <article className="card">
        <h3>Download output</h3>
        <dl className="kv-list">
          <div>
            <dt>Curated chunks</dt>
            <dd>{fmt(summary.final_output_chunks)}</dd>
          </div>
          <div>
            <dt>Characters</dt>
            <dd>{fmt(summary.final_output_chars)}</dd>
          </div>
          <div>
            <dt>Duplicates removed</dt>
            <dd>{fmt(summary.duplicates_removed)}</dd>
          </div>
          <div>
            <dt>PII entities redacted</dt>
            <dd>{fmt(summary.pii_entities_redacted)}</dd>
          </div>
        </dl>
        <div className="download-list">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => download(`curated-${stem}.jsonl`, curated, "application/jsonl")}
          >
            <Download size={16} /> Curated corpus (.jsonl)
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => download(`summary-${stem}.json`, JSON.stringify(summary, null, 2), "application/json")}
          >
            <Download size={16} /> Run summary (.json)
          </button>
        </div>
        <p className="cell-sub">
          One JSON object per line: the redacted text plus source file, chunk ID and regulatory tags.
        </p>
      </article>
    </div>
  );
}

function RunPipeline() {
  const [files, setFiles] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  function addFiles(list) {
    const pdfs = [...list].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    setError(pdfs.length < list.length ? "Only PDF files are accepted; other files were skipped." : null);
    setFiles((current) => {
      const names = new Set(current.map((f) => f.name));
      return [...current, ...pdfs.filter((f) => !names.has(f.name))];
    });
  }

  async function runPipeline() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const payload = {
        files: await Promise.all(files.map(async (f) => ({ name: f.name, data: await readAsBase64(f) }))),
      };
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => null);
      if (!body) throw new Error(`The pipeline API is not reachable. ${API_HINT}`);
      if (!res.ok) throw new Error(body.error || `Request failed (HTTP ${res.status})`);
      setResult(body);
    } catch (err) {
      setError(err instanceof TypeError ? `The pipeline API is not reachable. ${API_HINT}` : err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section id="run" className="section">
      <SectionHeader
        title="Process new documents"
        description="Upload KYC / AML PDFs and run them through the same six stages. Nothing is added to the curated corpus above; the output is yours to download."
      />

      <article className="card">
        <label
          className={`dropzone ${dragging ? "dropzone-active" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            addFiles(e.dataTransfer.files);
          }}
        >
          <input
            type="file"
            accept=".pdf,application/pdf"
            multiple
            className="sr-only"
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <span className="dropzone-icon">
            <Upload size={20} />
          </span>
          <span className="cell-title">Drop PDFs here or click to choose</span>
          <span className="cell-sub">Text-based PDFs; scanned images have no text to extract</span>
        </label>

        {files.length > 0 && (
          <ul className="file-list">
            {files.map((f) => (
              <li key={f.name}>
                <FileText size={16} className="muted" />
                <span className="truncate">{f.name}</span>
                <span className="cell-sub num">{fileSize(f.size)}</span>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label={`Remove ${f.name}`}
                  disabled={busy}
                  onClick={() => setFiles((current) => current.filter((x) => x !== f))}
                >
                  <X size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="actions">
          <button type="button" className="btn btn-primary" disabled={busy || files.length === 0} onClick={runPipeline}>
            {busy ? <LoaderCircle size={16} className="spin" /> : <Play size={16} />}
            {busy ? "Running pipeline…" : "Run pipeline"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy || (files.length === 0 && !result)}
            onClick={() => {
              setFiles([]);
              setResult(null);
              setError(null);
            }}
          >
            Clear
          </button>
        </div>
        {error && <p className="error-text">{error}</p>}
      </article>

      {result && <RunResult result={result} />}
    </section>
  );
}

/* ---------- app ---------- */

export default function App() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [theme, toggleTheme] = useTheme();
  const active = useActiveSection(Boolean(summary));

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
    <div className="shell">
      <Sidebar
        active={active}
        theme={theme}
        onToggleTheme={toggleTheme}
        documentCount={summary?.documents?.length}
      />
      <div className="main">
        <Topbar active={active} />
        <main className="content">
          {error && (
            <div className="card empty">
              <TriangleAlert size={18} />
              <p>
                Could not load pipeline_summary.json ({error}). Run <code>python -m pipeline.run</code>{" "}
                from the project root first.
              </p>
            </div>
          )}
          {!summary && !error && <p className="muted">Loading pipeline results…</p>}
          {summary && (
            <>
              <Overview summary={summary} />
              <Pipeline stages={summary.stages} />
              <CorpusQuality summary={summary} />
              <NemoComparison />
              <PiiSection summary={summary} />
              <Documents documents={summary.documents || []} />
              <SimilaritySearch />
              <RunPipeline />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
