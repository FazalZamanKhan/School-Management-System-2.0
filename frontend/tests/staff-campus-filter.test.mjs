import assert from "node:assert/strict";
import test from "node:test";
import { matchesStaffCampus } from "../src/staffCampusFilter.js";

test("numeric API campus IDs match string dropdown values", () => {
  assert.equal(matchesStaffCampus({ primary_campus: 42 }, "42"), true);
  assert.equal(matchesStaffCampus({ primary_campus: "42" }, 42), true);
});

test("selected campus excludes other campuses and unassigned staff", () => {
  assert.equal(matchesStaffCampus({ primary_campus: 7 }, "42"), false);
  assert.equal(matchesStaffCampus({ primary_campus: null }, "42"), false);
});

test("all campuses includes assigned and unassigned staff", () => {
  assert.equal(matchesStaffCampus({ primary_campus: 42 }, ""), true);
  assert.equal(matchesStaffCampus({}, ""), true);
});

test("legacy campus IDs still match", () => {
  assert.equal(matchesStaffCampus({ campus: 42 }, "42"), true);
});
