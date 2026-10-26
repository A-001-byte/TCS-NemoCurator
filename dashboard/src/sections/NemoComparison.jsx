import { useEffect, useState } from "react";
import {
  TriangleAlert,
  LoaderCircle,
} from "lucide-react";
import { reasonLabel } from "../stages";
import { Bar, SectionHeader } from "../components/common";
import { fmt, pct } from "../format";

export default function NemoComparison() {
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
