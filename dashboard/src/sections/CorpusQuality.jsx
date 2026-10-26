import { SectionHeader } from "../components/common";
import { fmt, pct } from "../format";
import { byStage } from "../summary";
import ReasonList from "../components/ReasonList";

export default function CorpusQuality({ summary }) {
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
