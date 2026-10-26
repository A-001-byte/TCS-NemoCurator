import { useState } from "react";
import {
  CircleCheck,
  Upload,
  FileText,
  X,
  Play,
  Download,
  LoaderCircle,
} from "lucide-react";
import { STAGES, reasonLabel } from "../stages";
import { SectionHeader } from "../components/common";
import { fmt } from "../format";

const API_HINT = "Start it with: python -m pipeline.server (or: bfsi-curate serve)";
// The same limits the server enforces (pipeline/server.py), so the form says so before anything is sent.
const MAX_FILES = 10;
const MAX_TOTAL_MB = 30;

function limitMessage(files) {
  if (files.length > MAX_FILES) return `At most ${MAX_FILES} files per run: remove ${files.length - MAX_FILES}.`;
  const bytes = files.reduce((sum, f) => sum + f.size, 0);
  if (bytes > MAX_TOTAL_MB * 1024 * 1024) return `Together the files are larger than ${MAX_TOTAL_MB} MB: remove some.`;
  return null;
}

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

export default function RunPipeline() {
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
        description="Upload KYC / AML PDFs and run them through the same stages as the corpus above. Nothing is added to the curated corpus above; the output is yours to download."
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
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || files.length === 0 || Boolean(limitMessage(files))}
            onClick={runPipeline}
          >
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
        {(error || limitMessage(files)) && <p className="error-text">{error || limitMessage(files)}</p>}
      </article>

      {result && <RunResult result={result} />}
    </section>
  );
}
