import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { TriangleAlert } from "lucide-react";
import { RefreshStatus, Sidebar, Topbar } from "./components/Shell";
import RunOptions from "./components/RunOptions";
import { buildSections } from "./navigation";
import CorpusQuality from "./sections/CorpusQuality";
import Documents from "./sections/Documents";
import DocumentTypes from "./sections/DocumentTypes";
import NemoComparison from "./sections/NemoComparison";
import Overview from "./sections/Overview";
import Pipeline from "./sections/Pipeline";
import PiiSection from "./sections/PiiSection";
import RunPipeline from "./sections/RunPipeline";
import SimilaritySearch from "./sections/SimilaritySearch";
import Tokens from "./sections/Tokens";
import { isDocTypeReport, isSummary, isTokenReport } from "./shapes";
import { byStage } from "./summary";
import { useActiveSection } from "./useActiveSection";
import { useRefresh } from "./useRefresh";
import { useSnapshot } from "./useSnapshot";
import { useTheme } from "./useTheme";
import "./App.css";

const DEFAULT_RUN_OPTIONS = { device: "auto", quality_signal: "off" };

export default function App() {
  const [theme, toggleTheme] = useTheme();
  // Bumped when a refresh finishes: every snapshot is read again and every section remounts.
  const [dataVersion, setDataVersion] = useState(0);
  const [runOptions, setRunOptions] = useState(DEFAULT_RUN_OPTIONS);
  const [draftOptions, setDraftOptions] = useState(DEFAULT_RUN_OPTIONS);
  const [capabilities, setCapabilities] = useState(null);
  const [refreshOpen, setRefreshOpen] = useState(false);
  const dialogRef = useRef(null);
  const summaryState = useSnapshot("pipeline_summary.json", isSummary, dataVersion);
  const summary = summaryState.data;
  const doctypes = useSnapshot("doctype_eval.json", isDocTypeReport, dataVersion);
  const tokens = useSnapshot("token_stats.json", isTokenReport, dataVersion);
  const refresh = useRefresh(useCallback(() => setDataVersion((v) => v + 1), []));

  useEffect(() => {
    let active = true;
    fetch("/api/capabilities")
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (active) setCapabilities(data); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!refreshOpen) return undefined;
    dialogRef.current?.focus();
    const closeOnEscape = (event) => { if (event.key === "Escape") setRefreshOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [refreshOpen]);
  const hasDoctypes = doctypes.status === "ready";
  const hasTokens = tokens.status === "ready";
  const sections = useMemo(
    () => buildSections({ doctypes: hasDoctypes, tokens: hasTokens }),
    [hasDoctypes, hasTokens]
  );
  const active = useActiveSection(Boolean(summary), sections);
  // null until the summary loads; "" when a run did not report a device
  const qualityStage = summary ? byStage(summary.stages, "quality_filter") : null;
  const device = qualityStage
    ? qualityStage.quality_signal_mode === "model"
      ? qualityStage.device || "not reported"
      : "model off (CPU)"
    : null;

  return (
    <div className="shell">
      <Sidebar
        sections={sections}
        active={active}
        theme={theme}
        onToggleTheme={toggleTheme}
        documentCount={summary?.documents?.length}
      />
      <div className="main">
        <Topbar
          sections={sections}
          active={active}
          device={device}
          onRefresh={() => {
            setDraftOptions({ ...runOptions });
            setRefreshOpen(true);
          }}
          refreshing={refresh.job.state === "running"}
          elapsed={refresh.job.elapsed_seconds}
        />
        <main className="content">
          <RefreshStatus job={refresh.job} />
          {summaryState.status === "missing" && (
            <div className="card empty">
              <TriangleAlert size={18} />
              <p>
                Could not load pipeline_summary.json. Run <code>python -m pipeline.run</code> from the
                project root first, or start the server with <code>python -m pipeline.server</code> and
                use the re-run button above.
              </p>
            </div>
          )}
          {summaryState.status === "loading" && <p className="muted">Loading pipeline results…</p>}
          {summary && (
            <Fragment key={dataVersion}>
              <Overview summary={summary} />
              <Pipeline stages={summary.stages} />
              <CorpusQuality summary={summary} />
              {hasTokens && <Tokens report={tokens.data} />}
              <NemoComparison />
              {hasDoctypes && <DocumentTypes report={doctypes.data} />}
              <PiiSection summary={summary} />
              <Documents documents={summary.documents || []} />
              <SimilaritySearch />
              <RunPipeline options={runOptions} onOptionsChange={setRunOptions} capabilities={capabilities} />
            </Fragment>
          )}
        </main>
      </div>
      {refreshOpen && (
        <div className="run-dialog-backdrop">
          <div className="run-dialog card" role="dialog" aria-modal="true" aria-labelledby="refresh-title" tabIndex={-1} ref={dialogRef}>
            <h2 id="refresh-title">Run the full corpus</h2>
            <p className="body">Choose settings for this run. Auto is selected by default.</p>
            <RunOptions options={draftOptions} onChange={setDraftOptions} capabilities={capabilities} />
            <div className="actions">
              <button type="button" className="btn btn-primary" onClick={() => {
                setRefreshOpen(false);
                setRunOptions(draftOptions);
                refresh.start(draftOptions);
              }}>
                Start run
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setRefreshOpen(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
