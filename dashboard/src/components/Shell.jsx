import {
  Moon,
  Sun,
  ChevronRight,
  CircleCheck,
  TriangleAlert,
  Database,
  Boxes,
  LoaderCircle,
  RefreshCw,
  Cpu,
} from "lucide-react";
import { duration, fmt } from "../format";

export function Sidebar({ sections, active, theme, onToggleTheme, documentCount }) {
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
        {sections.map(({ id, title, icon: Icon }) => (
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

/* `device` describes the quality model's actual device in the saved snapshot. */
export function Topbar({ sections, active, device, onRefresh, refreshing, elapsed }) {
  const section = sections.find((s) => s.id === active);

  return (
    <header className="topbar">
      <div className="crumbs">
        <span className="muted">Curation run</span>
        <ChevronRight size={16} className="muted" />
        <span>{section?.title}</span>
      </div>

      <div className="topbar-actions">
        {device !== null && (
          <span className="pill" title="Quality model device in the saved snapshot">
            <Cpu size={14} />
            Quality: {device || "not reported"}
          </span>
        )}
        <span className="pill pill-snapshot" title="The file the numbers on this page are read from">
          <span className="dot" />
          Snapshot: pipeline_summary.json
        </span>

        <button
          type="button"
          className="btn btn-secondary"
          onClick={onRefresh}
          disabled={refreshing}
          title="Runs all the source PDFs through the pipeline again and refreshes every number on this page"
        >
          <RefreshCw size={14} className={refreshing ? "spin" : undefined} />
          {refreshing ? `Re-running… ${duration(elapsed)}` : "Re-run pipeline"}
        </button>
      </div>
    </header>
  );
}

/* Progress, result or failure of a pipeline refresh started from the top bar. */
export function RefreshStatus({ job }) {
  if (job.state === "running") {
    return (
      <div className="callout" role="status">
        <LoaderCircle size={18} className="spin" />
        <p>
          Re-running the pipeline on every document. This takes several minutes; the numbers on this
          page update by themselves when it finishes ({duration(job.elapsed_seconds)} so far).
        </p>
      </div>
    );
  }
  if (job.state === "succeeded") {
    return (
      <div className="callout" role="status">
        <CircleCheck size={18} />
        <p>
          Snapshots refreshed: {fmt(job.chunks)} curated chunks, {fmt(job.pii_entities)} PII entities
          redacted ({duration(job.elapsed_seconds)}).
        </p>
      </div>
    );
  }
  if (job.state === "failed") {
    return (
      <div className="card empty" role="alert">
        <TriangleAlert size={18} />
        <p>The refresh failed: {job.error}</p>
      </div>
    );
  }
  return null;
}
