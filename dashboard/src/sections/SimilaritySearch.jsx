import { useEffect, useState } from "react";
import {
  Search,
  TriangleAlert,
} from "lucide-react";
import {
  prepareCorpus,
  rankMatches,
  classify,
  CANDIDATE_LIMIT,
  HIGH_SIMILARITY,
  MODERATE_SIMILARITY,
} from "../similarity";
import { Bar, SectionHeader } from "../components/common";
import { fmt } from "../format";

const EXAMPLE_QUERY =
  "The customer submitted KYC documents including PAN details, address proof and bank account information. The transaction history shows multiple unusual transfers requiring further review.";

const EXCERPT_CHARS = 480;

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

export default function SimilaritySearch() {
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
