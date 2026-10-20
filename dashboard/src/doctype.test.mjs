/* Run: node --test dashboard/src      (or `npm test` inside dashboard/) */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { buildCaption, buildModel, classifyText, documentsFromChunks, evaluate, LOW_CONFIDENCE_MARGIN } from "./doctype.js";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const doc = (source_file, label, text) => ({ source_file, label, text });

/* Three types with their own vocabulary; a1/a2 are near-copies of each other. */
const TOY = [
  doc("a1.pdf", "policy", "customer onboarding identity verification branch officer account opening customer onboarding"),
  doc("a2.pdf", "policy", "customer onboarding identity verification branch officer account opening customer onboarding review"),
  doc("b1.pdf", "format", "field length char numeric schema batch validation xml tag mandatory field"),
  doc("b2.pdf", "format", "xml schema tag numeric field char batch upload validation column"),
  doc("c1.pdf", "report", "annual report financial year statistics disseminated agencies chart table"),
  doc("c2.pdf", "report", "annual statistics chart agencies financial year disseminated report table"),
];

test("a held-out document is assigned to the type with the closest word profile", () => {
  const model = buildModel(TOY.filter((d) => d.source_file !== "b1.pdf"));
  const result = classifyText(TOY[2].text, model);
  assert.equal(result.predicted, "format");
  assert.equal(result.top3.length, 3);
  assert.ok(result.top3[0].score >= result.top3[1].score && result.top3[1].score >= result.top3[2].score);
});

test("text sharing no words with any type is flagged low confidence", () => {
  const result = classifyText("zebra quartz xylophone", buildModel(TOY));
  assert.equal(result.lowConfidence, true);
  assert.ok(result.margin < LOW_CONFIDENCE_MARGIN);
});

test("holding out a family removes its near-copies from training and exposes the optimism", () => {
  const result = evaluate(TOY, [["a1.pdf", "a2.pdf"]]);
  const row = (file) => result.per_document.find((r) => r.source_file === file);

  assert.equal(row("a1.pdf").training_documents, TOY.length - 2, "sibling a2 must be held out with a1");
  assert.equal(row("b1.pdf").training_documents, TOY.length - 1, "a document with no family only leaves itself out");

  // The type "policy" exists only in this one family, so it cannot be scored family-wise.
  assert.equal(row("a1.pdf").scored, false);
  assert.deepEqual(result.unscored.sort(), ["a1.pdf", "a2.pdf"]);
  assert.equal(result.n_scored, 4);

  // Leaving only the document out lets its copy answer for it: a higher, optimistic score.
  assert.equal(row("a1.pdf").correct_by_document, true);
  assert.equal(result.accuracy.by_document, 1);
  assert.equal(result.accuracy.by_family, 1, "scored documents are b1, b2, c1, c2, all correct");
});

test("a wrong answer lowers the family accuracy and is counted against the type", () => {
  const swapped = TOY.map((d) => (d.source_file === "c2.pdf" ? { ...d, label: "format" } : d));
  const result = evaluate(swapped, []);
  assert.ok(result.accuracy.by_family < 1);
  assert.ok(result.per_type.find((t) => t.label === "format").recall < 1 || result.per_type.find((t) => t.label === "report").recall < 1);
});

test("chunks of one file are joined back into a single document", () => {
  const rows = [
    { text: "first", metadata: { source_file: "x.pdf" } },
    { text: "other", metadata: { source_file: "y.pdf" } },
    { text: "second", metadata: { source_file: "x.pdf" } },
  ];
  assert.deepEqual(documentsFromChunks(rows), [
    { source_file: "x.pdf", text: "first second" },
    { source_file: "y.pdf", text: "other" },
  ]);
});

test("the dashboard caption names the real document count and says what this is not", () => {
  assert.equal(
    buildCaption(34),
    "Document-type classification and clause similarity over a corpus of 34 documents. Not a trained fraud/anomaly model.",
  );
});

const curated = path.join(REPO, "data", "output", "curated.jsonl");
test("real corpus: every document has a label, and the family score beats always guessing the biggest type", { skip: !fs.existsSync(curated) }, () => {
  const rows = fs.readFileSync(curated, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
  const { labels } = JSON.parse(fs.readFileSync(path.join(REPO, "pipeline", "doc_type_labels.json"), "utf8"));
  const { families } = JSON.parse(fs.readFileSync(path.join(REPO, "pipeline", "doc_type_families.json"), "utf8"));
  const docs = documentsFromChunks(rows);

  assert.deepEqual(docs.map((d) => d.source_file).sort(), Object.keys(labels).sort(), "labels file and corpus must list the same documents");
  const result = evaluate(docs.map((d) => ({ ...d, label: labels[d.source_file] })), families);
  assert.ok(result.n_scored > 0);
  assert.ok(result.accuracy.by_family > result.majority_baseline, `${result.accuracy.by_family} vs ${result.majority_baseline}`);
});
