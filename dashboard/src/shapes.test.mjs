/* Run: npm test (inside dashboard/) */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { fmt, pct, share } from "./format.js";
import { isDocTypeReport, isTokenReport } from "./shapes.js";

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

test("number formatting never prints NaN or undefined", () => {
  assert.equal(fmt(3325), "3,325");
  assert.equal(fmt(undefined), "–");
  assert.equal(pct(1, 0), "–");
  assert.equal(pct(1, 4), "25.0%");
  assert.equal(share(0.5588), "55.9%");
  assert.equal(share(null), "–");
});
