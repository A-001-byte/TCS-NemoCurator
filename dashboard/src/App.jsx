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
                width: `${
                  stage.docs_in
                    ? (stage.docs_out / stage.docs_in) * 100
                    : 0
                }%`,
              }}
            />
          </div>

          {stage.removed > 0 && (
            <div className="funnel-removed">
              −{stage.removed} removed
              {Object.keys(stage.reason_counts || {}).length > 0 && (
                <span className="funnel-reasons">
                  {" "}
                  (
                  {Object.entries(stage.reason_counts)
                    .filter(([, v]) => v > 0)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(", ")}
                  )
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
        Real text extracted from actual RBI/bank KYC documents, redaction
        applied by the pipeline.

        {!nameDetectionAvailable && (
          <strong>
            {" "}
            Person-name detection (spaCy NER) was unavailable at run time —
            name entities are not included below.
          </strong>
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
              <span className="redacted-tag">
                [REDACTED_{ex.entity_type}]
              </span>
              {ex.context_after}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CorpusSummary({ summary }) {
  const extractStage = summary.stages.find(
    (s) => s.stage === "extract"
  );

  const outputStage = summary.stages.find(
    (s) => s.stage === "output"
  );

  return (
    <div className="stat-row">
      <div className="stat-card">
        <div className="stat-value">
          {extractStage?.docs_in ?? "-"}
        </div>
        <div className="stat-label">PDFs Ingested</div>
      </div>

      <div className="stat-card">
        <div className="stat-value">
          {summary.duplicates_removed}
        </div>
        <div className="stat-label">Duplicate Chunks Removed</div>
      </div>

      <div className="stat-card">
        <div className="stat-value">
          {summary.pii_entities_redacted}
        </div>
        <div className="stat-label">PII Entities Redacted</div>
      </div>

      <div className="stat-card">
        <div className="stat-value">
          {outputStage?.docs_out ?? "-"}
        </div>
        <div className="stat-label">Final Curated Chunks</div>
      </div>

      <div className="stat-card">
        <div className="stat-value">
          {summary.final_output_chars
            ? summary.final_output_chars.toLocaleString()
            : "-"}
        </div>
        <div className="stat-label">Total Characters Curated</div>
      </div>
    </div>
  );
}

function DocumentDrilldown({ documents }) {
  const [selectedId, setSelectedId] = useState(null);

  const selected =
    documents.find((d) => d.doc_id === selectedId) || null;

  return (
    <div className="panel">
      <h2>Document Drill-down</h2>

      <p className="panel-sub">
        Click a source document to see its journey through the pipeline.
      </p>

      <div className="doc-drilldown">
        <ul className="doc-list">
          {documents.map((doc) => (
            <li key={doc.doc_id}>
              <button
                className={`doc-list-item ${
                  selectedId === doc.doc_id ? "active" : ""
                }`}
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
                <span>
                  {selected.char_count.toLocaleString()}
                </span>
              </div>

              <div className="doc-detail-row">
                <span>Chunks surviving dedup</span>
                <span>{selected.chunks_after_dedup}</span>
              </div>

              <div className="doc-detail-row">
                <span>Chunks surviving quality filter</span>
                <span>
                  {selected.chunks_after_quality_filter}
                </span>
              </div>

              <div className="doc-detail-row">
                <span>Chunks with PII redacted</span>
                <span>
                  {selected.chunks_with_pii_redacted}
                </span>
              </div>
            </>
          ) : (
            <p className="doc-detail-empty">
              Select a document to see details.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/* =========================================================
   STREAM D — FAST PATTERN MATCHING
   ========================================================= */

function tokenize(text) {
  return String(text)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 2);
}

function createTermCounts(tokens) {
  const counts = new Map();

  for (const token of tokens) {
    counts.set(token, (counts.get(token) || 0) + 1);
  }

  return counts;
}

function prepareCorpus(corpus) {
  const prepared = [];
  const documentFrequency = new Map();

  for (const document of corpus) {
    const tokens = tokenize(document.text);
    const counts = createTermCounts(tokens);

    const uniqueWords = new Set(counts.keys());

    for (const word of uniqueWords) {
      documentFrequency.set(
        word,
        (documentFrequency.get(word) || 0) + 1
      );
    }

    prepared.push({
      ...document,
      counts,
      tokenCount: tokens.length,
      uniqueWords,
    });
  }

  return {
    documents: prepared,
    documentFrequency,
    totalDocuments: prepared.length,
  };
}

function getIdf(word, preparedCorpus) {
  const df =
    preparedCorpus.documentFrequency.get(word) || 0;

  return Math.log(
    (preparedCorpus.totalDocuments + 1) / (df + 1)
  ) + 1;
}

function getCandidateDocuments(inputText, preparedCorpus) {
  const inputTokens = tokenize(inputText);
  const inputWords = new Set(inputTokens);

  const scoredCandidates = preparedCorpus.documents.map(
    (document) => {
      let overlap = 0;

      for (const word of inputWords) {
        if (document.uniqueWords.has(word)) {
          overlap++;
        }
      }

      return {
        document,
        overlap,
      };
    }
  );

  scoredCandidates.sort((a, b) => b.overlap - a.overlap);

  /*
    Only calculate expensive cosine similarity for the
    most relevant candidates.

    The complete 2,189-chunk corpus is still loaded,
    but we avoid freezing the browser by scoring only
    the top candidates.
  */
  return scoredCandidates
    .filter((item) => item.overlap > 0)
    .slice(0, 60)
    .map((item) => item.document);
}

function cosineSimilarityForDocument(
  inputText,
  document,
  preparedCorpus
) {
  const inputTokens = tokenize(inputText);
  const inputCounts = createTermCounts(inputTokens);

  const inputTotal = inputTokens.length || 1;
  const documentTotal = document.tokenCount || 1;

  let dotProduct = 0;
  let inputMagnitude = 0;
  let documentMagnitude = 0;

  const allWords = new Set([
    ...inputCounts.keys(),
    ...document.counts.keys(),
  ]);

  for (const word of allWords) {
    const inputTf =
      (inputCounts.get(word) || 0) / inputTotal;

    const documentTf =
      (document.counts.get(word) || 0) / documentTotal;

    const idf = getIdf(word, preparedCorpus);

    const inputValue = inputTf * idf;
    const documentValue = documentTf * idf;

    dotProduct += inputValue * documentValue;
    inputMagnitude += inputValue * inputValue;
    documentMagnitude += documentValue * documentValue;
  }

  if (
    inputMagnitude === 0 ||
    documentMagnitude === 0
  ) {
    return 0;
  }

  return (
    dotProduct /
    (Math.sqrt(inputMagnitude) *
      Math.sqrt(documentMagnitude))
  );
}

function findBestMatch(inputText, preparedCorpus) {
  const candidates = getCandidateDocuments(
    inputText,
    preparedCorpus
  );

  if (candidates.length === 0) {
    return {
      classification: "Low Similarity",
      similarity: 0,
      matchedDocument: null,
    };
  }

  let bestDocument = null;
  let bestScore = 0;

  for (const document of candidates) {
    const score = cosineSimilarityForDocument(
      inputText,
      document,
      preparedCorpus
    );

    if (score > bestScore) {
      bestScore = score;
      bestDocument = document;
    }
  }

  let classification = "Low Similarity";

  if (bestScore >= 0.7) {
    classification = "High Similarity";
  } else if (bestScore >= 0.4) {
    classification = "Moderate Similarity";
  }

  return {
    classification,
    similarity: Number(bestScore.toFixed(3)),
    matchedDocument: bestDocument,
  };
}

function PatternMatchingPanel() {
  const [realCorpus, setRealCorpus] = useState([]);
  const [preparedCorpus, setPreparedCorpus] =
    useState(null);

  const [inputText, setInputText] = useState(
    "The customer submitted KYC documents including PAN details, address proof and bank account information. The transaction history shows multiple unusual transfers requiring further review."
  );

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/curated.jsonl", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        return res.text();
      })
      .then((text) => {
        const lines = text
          .split("\n")
          .filter((line) => line.trim());

        const parsed = lines
          .map((line) => {
            try {
              return JSON.parse(line);
            } catch {
              return null;
            }
          })
          .filter(Boolean)
          .map((item) => ({
            text: item.text || "",
            source_file:
              item.metadata?.source_file ||
              "Unknown document",
            chunk_id:
              item.metadata?.chunk_id ||
              "",
            doc_id:
              item.metadata?.doc_id ||
              "",
          }))
          .filter((item) => item.text.trim());

        setRealCorpus(parsed);

        /*
          Prepare the corpus once when the dashboard loads.
          This prevents the expensive preparation from happening
          every time the button is clicked.
        */
        setTimeout(() => {
          const prepared = prepareCorpus(parsed);
          setPreparedCorpus(prepared);
          setLoading(false);
        }, 0);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  function analyzePattern() {
    if (!preparedCorpus || !inputText.trim()) {
      return;
    }

    setAnalyzing(true);
    setResult(null);

    /*
      Let React update the button first before doing
      the calculation.
    */
    setTimeout(() => {
      try {
        const match = findBestMatch(
          inputText,
          preparedCorpus
        );

        setResult(match);
      } catch (err) {
        setError(err.message);
      } finally {
        setAnalyzing(false);
      }
    }, 50);
  }

  return (
    <div className="panel">
      <h2>Stream D — Pattern Matching</h2>

      <p className="panel-sub">
        Compare a new KYC document against the frozen curated
        corpus using TF-IDF and cosine similarity.
      </p>

      {loading && (
        <p className="panel-sub">
          Loading and preparing curated corpus...
        </p>
      )}

      {error && (
        <div className="error-banner">
          Could not load curated corpus ({error})
        </div>
      )}

      {!loading && !error && (
        <>
          <p className="panel-sub">
            <strong>{realCorpus.length.toLocaleString()}</strong>{" "}
            curated chunks loaded
          </p>

          <textarea
            value={inputText}
            onChange={(e) =>
              setInputText(e.target.value)
            }
            rows={5}
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: "12px",
              borderRadius: "6px",
              border: "1px solid #777",
              resize: "vertical",
              fontSize: "14px",
              marginBottom: "16px",
            }}
          />

          <button
            onClick={analyzePattern}
            disabled={
              analyzing ||
              !preparedCorpus ||
              !inputText.trim()
            }
            style={{
              display: "block",
              margin: "0 auto",
              padding: "10px 18px",
              border: "none",
              borderRadius: "6px",
              background: "#2563eb",
              color: "#ffffff",
              fontSize: "14px",
              fontWeight: "600",
              cursor:
                analyzing ||
                !preparedCorpus ||
                !inputText.trim()
                  ? "not-allowed"
                  : "pointer",
              opacity:
                analyzing ||
                !preparedCorpus ||
                !inputText.trim()
                  ? 0.6
                  : 1,
            }}
          >
            {analyzing
              ? "Analyzing..."
              : "Analyze Pattern"}
          </button>

          {result && (
            <div
              style={{
                marginTop: "24px",
                padding: "20px",
                borderRadius: "8px",
                border: "1px solid #444",
              }}
            >
              <h3 style={{ marginTop: 0 }}>
                Pattern Analysis Result
              </h3>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(3, 1fr)",
                  gap: "12px",
                  marginBottom: "18px",
                }}
              >
                <div className="stat-card">
                  <div className="stat-value">
                    {result.classification}
                  </div>
                  <div className="stat-label">
                    Classification
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-value">
                    {result.similarity}
                  </div>
                  <div className="stat-label">
                    Similarity Score
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-value">
                    {preparedCorpus.documents.length.toLocaleString()}
                  </div>
                  <div className="stat-label">
                    Curated Chunks
                  </div>
                </div>
              </div>

              {result.matchedDocument ? (
                <div>
                  <strong>Matched Document:</strong>{" "}
                  {result.matchedDocument.source_file}

                  <br />

                  <span
                    style={{
                      fontSize: "13px",
                      opacity: 0.75,
                    }}
                  >
                    Chunk ID:{" "}
                    {result.matchedDocument.chunk_id}
                  </span>
                </div>
              ) : (
                <p>
                  No sufficiently similar document pattern
                  was found.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function App() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/pipeline_summary.json", {
      cache: "no-store",
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        return res.json();
      })
      .then(setSummary)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          NeMo-Curator-Equivalent Pipeline — BFSI/KYC Corpus
        </h1>

        <p className="app-subtitle">
          Real RBI &amp; bank KYC/AML PDFs → cleaned,
          deduplicated, PII-redacted, fine-tuning-ready
          JSONL.
        </p>

        <p className="honesty-banner">
          Extraction, cleaning, language ID, dedup, quality
          filtering and PII redaction below are{" "}
          <strong>equivalent-logic stages</strong> (NeMo
          Curator's own <code>ProcessingStage</code>/
          <code>Pipeline</code> API failed to install on this
          machine — see README). Person-name PII uses spaCy
          NER; NVIDIA's shipped path uses GLiNER-PII. No
          fine-tuning was performed.
        </p>
      </header>

      {error && (
        <div className="error-banner">
          Could not load pipeline_summary.json ({error}).
          Run{" "}
          <code>python -m pipeline.run</code> from the
          project root first.
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
            entityCounts={
              summary.pii_entity_type_counts
            }
            nameDetectionAvailable={
              summary.name_detection_available
            }
          />

          <DocumentDrilldown
            documents={summary.documents || []}
          />

          <PatternMatchingPanel />
        </main>
      )}
    </div>
  );
}