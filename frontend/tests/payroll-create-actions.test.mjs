import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../src/pages/PayrollPage.jsx", import.meta.url),
  "utf8",
);

test("Payroll exposes create actions for structures and records", () => {
  assert.match(source, /Add Salary Structure/);
  assert.match(source, /onClick=\{\(\) => openStructureModal\("create"\)\}/);
  assert.match(source, /Add Payroll Record/);
  assert.match(source, /onClick=\{\(\) => openRecordModal\("create"\)\}/);
});
