import { useMemo, useState } from "react";
import { Bar, SectionHeader } from "../components/common";
import { fmt, pct } from "../format";

const DOC_COLUMNS = [
  { key: "source_file", label: "Document" },
  { key: "char_count", label: "Characters", numeric: true },
  { key: "chunks_after_dedup", label: "After dedup", numeric: true },
  { key: "chunks_after_quality_filter", label: "After quality filter", numeric: true },
  { key: "chunks_with_pii_redacted", label: "Chunks with PII", numeric: true },
];

export default function Documents({ documents }) {
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
