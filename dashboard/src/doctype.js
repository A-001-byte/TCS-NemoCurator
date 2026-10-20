/*
  Document-type classification over the curated corpus.

  Each document type is represented by a centroid: the average word profile of its training
  documents, every document weighted equally so a very long file cannot dominate its type.
  A new document is compared with every centroid using the same TF-IDF weighting and cosine
  similarity as the clause search (similarity.js), and the three closest types are returned.

  This is a small nearest-centroid classifier over a corpus of regulatory documents. It is
  not a trained fraud or anomaly model.
*/
import { cosineSimilarity, createTermCounts, prepareCorpus, tokenize } from "./similarity.js";

export const TOP_K = 3;
/* Fixed before looking at any result and never tuned on one: when the best type is less than
   this far ahead of the runner-up, the answer is flagged as low confidence. */
export const LOW_CONFIDENCE_MARGIN = 0.05;
/* Words that appear in more than this share of the training documents carry no information
   about type (every KYC document says "customer", "account", "due diligence"). Chosen once,
   before measuring; 1 keeps every word and reproduces plain TF-IDF. */
export const DEFAULT_MAX_DOC_SHARE = 0.5;

export const buildCaption = (documentCount) =>
  `Document-type classification and clause similarity over a corpus of ${documentCount} documents. Not a trained fraud/anomaly model.`;

/** Join the curated chunks of each source file back into one document text. */
export function documentsFromChunks(rows) {
  const texts = new Map();
  for (const row of rows) {
    const file = row.metadata.source_file;
    texts.set(file, texts.has(file) ? `${texts.get(file)} ${row.text}` : row.text);
  }
  return [...texts].map(([source_file, text]) => ({ source_file, text }));
}

/** Learn one centroid per label from [{source_file, text, label}]. */
export function buildModel(trainingDocs, maxDocShare = DEFAULT_MAX_DOC_SHARE) {
  const prepared = prepareCorpus(trainingDocs);
  const common = new Set(
    [...prepared.documentFrequency].filter(([, df]) => df / prepared.totalDocuments > maxDocShare).map(([word]) => word),
  );
  const sums = new Map();
  for (const doc of prepared.documents) {
    const entry = sums.get(doc.label) ?? { counts: new Map(), documents: 0 };
    for (const [word, count] of doc.counts) {
      if (!common.has(word)) entry.counts.set(word, (entry.counts.get(word) || 0) + count / doc.tokenCount);
    }
    sums.set(doc.label, { counts: entry.counts, documents: entry.documents + 1 });
  }
  const centroids = [...sums].map(([label, { counts, documents }]) => ({
    label,
    documents,
    // tokenCount 1: the counts are already averaged term frequencies
    tokenCount: 1,
    counts: new Map([...counts].map(([word, value]) => [word, value / documents])),
  }));
  return { prepared, centroids, common };
}

/** Top-3 types with scores, and whether the winner's lead over the runner-up is too small. */
export function classifyText(text, model) {
  const tokens = tokenize(text).filter((word) => !model.common.has(word));
  const counts = createTermCounts(tokens);
  const total = tokens.length || 1;
  const ranked = model.centroids
    .map((centroid) => ({ label: centroid.label, score: cosineSimilarity(counts, total, centroid, model.prepared) }))
    .sort((a, b) => b.score - a.score);
  const margin = ranked.length > 1 ? ranked[0].score - ranked[1].score : (ranked[0]?.score ?? 0);
  return {
    predicted: ranked[0]?.label ?? null,
    top3: ranked.slice(0, TOP_K),
    margin,
    lowConfidence: margin < LOW_CONFIDENCE_MARGIN,
  };
}

const share = (part, whole) => (whole === 0 ? null : part / whole);

function predictHeldOut(doc, docs, excluded, maxDocShare) {
  const training = docs.filter((other) => !excluded.has(other.source_file));
  const trainedOnType = training.some((other) => other.label === doc.label);
  const result = classifyText(doc.text, buildModel(training, maxDocShare));
  return { ...result, trainingDocuments: training.length, scored: trainedOnType };
}

/**
 * Hold each document out twice: alone (its near-copies stay in training, so this is optimistic)
 * and together with its whole near-copy family (the honest number). A document whose type has
 * no other family left is reported as unscored instead of counted wrong.
 */
export function evaluate(docs, families, maxDocShare = DEFAULT_MAX_DOC_SHARE) {
  const familyOf = new Map();
  families.forEach((members, index) => members.forEach((file) => familyOf.set(file, index)));
  const siblings = (doc) => new Set(families[familyOf.get(doc.source_file)] ?? [doc.source_file]);

  const perDocument = docs.map((doc) => {
    const alone = predictHeldOut(doc, docs, new Set([doc.source_file]), maxDocShare);
    const family = predictHeldOut(doc, docs, siblings(doc), maxDocShare);
    return {
      source_file: doc.source_file,
      true: doc.label,
      family: familyOf.get(doc.source_file) ?? null,
      predicted: family.predicted,
      top3: family.top3,
      low_confidence: family.lowConfidence,
      correct: family.predicted === doc.label,
      scored: family.scored,
      training_documents: family.trainingDocuments,
      predicted_by_document: alone.predicted,
      correct_by_document: alone.predicted === doc.label,
    };
  });

  const scored = perDocument.filter((row) => row.scored);
  const right = (rows, key) => rows.filter((row) => row[key]).length;
  const confident = scored.filter((row) => !row.low_confidence);
  const flagged = scored.filter((row) => row.low_confidence);
  const labels = [...new Set(docs.map((doc) => doc.label))].sort();
  const perType = labels.map((label) => {
    const rows = scored.filter((row) => row.true === label);
    return { label, documents: docs.filter((doc) => doc.label === label).length, scored: rows.length, recall: share(right(rows, "correct"), rows.length) };
  });
  const largestType = Math.max(...perType.map((type) => scored.filter((row) => row.true === type.label).length));

  return {
    labels,
    caption: buildCaption(docs.length),
    settings: { low_confidence_margin: LOW_CONFIDENCE_MARGIN, top_k: TOP_K, max_doc_share: maxDocShare },
    n_documents: docs.length,
    n_scored: scored.length,
    n_families: families.length,
    accuracy: {
      by_document: share(right(perDocument, "correct_by_document"), perDocument.length),
      by_family: share(right(scored, "correct"), scored.length),
    },
    majority_baseline: share(largestType, scored.length),
    confident: { count: confident.length, accuracy: share(right(confident, "correct"), confident.length) },
    flagged: { count: flagged.length, accuracy: share(right(flagged, "correct"), flagged.length) },
    per_type: perType,
    unscored: perDocument.filter((row) => !row.scored).map((row) => row.source_file),
    per_document: perDocument,
  };
}
