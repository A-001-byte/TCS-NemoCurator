/* Run: npm test (inside dashboard/) */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { duration, fmt, pct, share } from "./format.js";
import { isDocTypeReport, isSummary, isTokenReport } from "./shapes.js";

const PUBLIC = path.resolve(import.meta.dirname, "..", "public");
// Same tolerance as the dashboard: a byte-order mark must not break a snapshot.
const load = (file) => JSON.parse(fs.readFileSync(path.join(PUBLIC, file), "utf8").replace(/^﻿/, ""));

test("the committed snapshots have the shapes their panels need", () => {
  assert.ok(isDocTypeReport(load("doctype_eval.json")));
  assert.ok(isTokenReport(load("token_stats.json")));
});

test("the document-type caption names the corpus and says what this is not", () => {
  const report = load("doctype_eval.json");
  assert.match(report.caption, /^Document-type classification and clause similarity over a corpus of \d+ documents\. Not a trained fraud\/anomaly model\.$/);
  assert.equal(report.per_document.length, report.n_documents);
});

test("token counts add up", () => {
  const report = load("token_stats.json");
  assert.equal(report.per_document.reduce((sum, d) => sum + d.tokens, 0), report.total_tokens);
});

test("a missing, empty or differently shaped file hides the panel instead of breaking it", () => {
  for (const bad of [null, undefined, {}, [], { per_document: [] }, { per_document: "x", total_tokens: 1, tokenizer: "t" }]) {
    assert.equal(isDocTypeReport(bad), false, JSON.stringify(bad));
    assert.equal(isTokenReport(bad), false, JSON.stringify(bad));
  }
  const report = load("doctype_eval.json");
  assert.equal(isDocTypeReport({ ...report, caption: undefined }), false, "no caption, no panel");
  assert.equal(isDocTypeReport({ ...report, accuracy: {} }), false);
});

test("the pipeline summary is recognised, an empty or foreign file is not", () => {
  assert.ok(isSummary(load("pipeline_summary.json")));
  for (const bad of [null, {}, { stages: [] }, { stages: "x" }, []]) assert.equal(isSummary(bad), false, JSON.stringify(bad));
});

test("a refresh's elapsed time reads as m:ss", () => {
  assert.equal(duration(0), "0:00");
  assert.equal(duration(5), "0:05");
  assert.equal(duration(754), "12:34");
  assert.equal(duration(undefined), "–");
  assert.equal(duration(-1), "–");
});

test("number formatting never prints NaN or undefined", () => {
  assert.equal(fmt(3325), "3,325");
  assert.equal(fmt(undefined), "–");
  assert.equal(pct(1, 0), "–");
  assert.equal(pct(1, 4), "25.0%");
  assert.equal(share(0.5588), "55.9%");
  assert.equal(share(null), "–");
});
