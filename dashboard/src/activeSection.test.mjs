import assert from "node:assert/strict";
import test from "node:test";
import { chooseActive } from "./activeSection.js";

const ids = ["overview", "pipeline", "corpus", "run"];

test("the first section is active at the top of the page", () => {
  assert.equal(chooseActive(ids, [80, 600, 1300, 1800], 270, false), "overview");
});

test("a section becomes active once its top passes the activation line", () => {
  assert.equal(chooseActive(ids, [-700, 250, 900, 1400], 270, false), "pipeline");
  assert.equal(chooseActive(ids, [-700, 300, 900, 1400], 270, false), "overview");
});

test("the last section is active at the end of the page even though it never reaches the line", () => {
  assert.equal(chooseActive(ids, [-2000, -1400, -700, 407], 270, true), "run");
  assert.equal(chooseActive(ids, [-2000, -1400, -700, 407], 270, false), "corpus");
});

test("a section that is not on the page is skipped", () => {
  assert.equal(chooseActive(ids, [-500, null, 100, 900], 270, false), "corpus");
  assert.equal(chooseActive(ids, [null, null, null, null], 270, false), "overview");
});
