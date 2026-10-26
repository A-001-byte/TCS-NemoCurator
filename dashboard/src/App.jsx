import { Fragment, useCallback, useMemo, useState } from "react";
import { TriangleAlert } from "lucide-react";
import { RefreshStatus, Sidebar, Topbar } from "./components/Shell";
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

export default function App() {
  const [theme, toggleTheme] = useTheme();
  // Bumped when a refresh finishes: every snapshot is read again and every section remounts.
  const [dataVersion, setDataVersion] = useState(0);
  const summaryState = useSnapshot("pipeline_summary.json", isSummary, dataVersion);
  const summary = summaryState.data;
  const doctypes = useSnapshot("doctype_eval.json", isDocTypeReport, dataVersion);
  const tokens = useSnapshot("token_stats.json", isTokenReport, dataVersion);
  const refresh = useRefresh(useCallback(() => setDataVersion((v) => v + 1), []));
  const hasDoctypes = doctypes.status === "ready";
  const hasTokens = tokens.status === "ready";
  const sections = useMemo(
    () => buildSections({ doctypes: hasDoctypes, tokens: hasTokens }),
    [hasDoctypes, hasTokens]
  );
  const active = useActiveSection(Boolean(summary), sections);
  // null until the summary loads; "" when a run did not report a device
  const device = summary ? byStage(summary.stages, "quality_filter").device || "" : null;


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
          onRefresh={refresh.start}
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
              <RunPipeline />
            </Fragment>
          )}
        </main>
      </div>
    </div>
  );
}
