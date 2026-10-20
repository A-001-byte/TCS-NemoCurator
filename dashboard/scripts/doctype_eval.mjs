/*
  Score the document-type classifier and write dashboard/public/doctype_eval.json.

    node dashboard/scripts/doctype_eval.mjs [--chunks data/output/curated.jsonl] [--out dashboard/public/doctype_eval.json]

  Reads the curated chunks, the hand-made labels (pipeline/doc_type_labels.json) and the
  near-copy families (pipeline/doc_type_families.json, from `python -m pipeline.doctype_families`).
  Stops with a message if the labels and the corpus do not list the same documents.
*/
import fs from "node:fs";
import path from "node:path";

import { documentsFromChunks, evaluate } from "../src/doctype.js";

const REPO = path.resolve(import.meta.dirname, "..", "..");

function option(name, fallback) {
  const at = process.argv.indexOf(`--${name}`);
  return at === -1 ? fallback : path.resolve(process.argv[at + 1]);
}

const readJson = (file) => JSON.parse(fs.readFileSync(file, "utf8"));
const chunksPath = option("chunks", path.join(REPO, "data", "output", "curated.jsonl"));
const outPath = option("out", path.join(REPO, "dashboard", "public", "doctype_eval.json"));

const rows = fs.readFileSync(chunksPath, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
const { labels, types } = readJson(path.join(REPO, "pipeline", "doc_type_labels.json"));
const { families } = readJson(path.join(REPO, "pipeline", "doc_type_families.json"));
const docs = documentsFromChunks(rows);

const unlabelled = docs.filter((d) => !(d.source_file in labels)).map((d) => d.source_file);
const missing = Object.keys(labels).filter((file) => !docs.some((d) => d.source_file === file));
if (unlabelled.length || missing.length) {
  console.error(`Labels and corpus disagree.\n  in the corpus but unlabelled: ${unlabelled.join(", ") || "none"}\n  labelled but not in the corpus: ${missing.join(", ") || "none"}`);
  process.exit(1);
}

const labelled = docs.map((d) => ({ ...d, label: labels[d.source_file] }));
const result = evaluate(labelled, families);
// Plain TF-IDF (every word kept) is kept in the output: with 34 documents, reporting only the
// better of the versions we tried would overstate it.
const plain = evaluate(labelled, families, 1);
result.plain_tfidf = { accuracy: plain.accuracy, confident: plain.confident, flagged: plain.flagged };
// 4 = plain and filtered TF-IDF on the first 7-type label set, then both again after bank and
// NBFC policy were merged into one type. The merge was chosen after seeing the confusion table.
result.variants_tried = 4;
result.variants_note =
  "Four combinations were scored on these same documents (plain or filtered TF-IDF, with bank and NBFC policy separate or merged). The merge was chosen after seeing the confusion table, so treat the headline as the optimistic end.";
result.type_descriptions = types;
fs.writeFileSync(outPath, `${JSON.stringify(result, null, 2)}\n`);

const pct = (value) => (value === null ? "n/a" : `${(100 * value).toFixed(1)}%`);
console.log(`${result.n_documents} documents, ${result.n_families} near-copy families, ${result.n_scored} scored`);
console.log(`accuracy holding the family out: ${pct(result.accuracy.by_family)}   (leaving only the document out: ${pct(result.accuracy.by_document)})`);
console.log(`plain TF-IDF, every word kept: ${pct(plain.accuracy.by_family)} (family held out), ${pct(plain.accuracy.by_document)} (document only)`);
console.log(`always guessing the biggest type: ${pct(result.majority_baseline)}`);
console.log(`confident answers: ${result.confident.count} at ${pct(result.confident.accuracy)}; flagged low confidence: ${result.flagged.count} at ${pct(result.flagged.accuracy)}`);
console.log(`written to ${path.relative(REPO, outPath)}`);
