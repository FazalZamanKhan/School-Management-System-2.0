import assert from "node:assert/strict";
import test from "node:test";
import { hasImportableRows } from "../src/importPreview.js";

test("missing, empty, and entirely invalid previews cannot be imported", () => {
  assert.equal(hasImportableRows(null), false);
  assert.equal(hasImportableRows({ total_rows: 0, valid_rows: 0 }), false);
  assert.equal(hasImportableRows({ total_rows: 1, valid_rows: 0, error_rows: 1, can_commit: false }), false);
});

test("fully valid previews and valid-row-only partial imports remain available", () => {
  assert.equal(hasImportableRows({ valid_rows: 1, can_commit: true }), true);
  assert.equal(hasImportableRows({ total_rows: 2, valid_rows: 1, error_rows: 1, can_commit: false }), true);
});

test("invalid valid-row counts fail closed", () => {
  for (const valid_rows of [undefined, -1, 0.5, Infinity, "1"]) {
    assert.equal(hasImportableRows({ valid_rows }), false);
  }
});
