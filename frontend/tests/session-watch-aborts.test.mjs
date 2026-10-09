import assert from "node:assert/strict";
import test from "node:test";
import { installSessionWatch } from "../src/sessionWatch.js";

test("session watcher handles its observer rejection while preserving caller errors", async () => {
  const events = [];
  const unhandled = [];
  const listener = (error) => unhandled.push(error);
  process.on("unhandledRejection", listener);
  const previousWindow = globalThis.window;
  const previousEvent = globalThis.CustomEvent;
  let nextFetch;
  globalThis.window = {
    fetch: (...args) => nextFetch(...args),
    dispatchEvent: (event) => events.push(event.type),
  };
  globalThis.CustomEvent = class { constructor(type) { this.type = type; } };
  try {
    installSessionWatch();
    for (const error of [new DOMException("Superseded", "AbortError"), new TypeError("Network failed")]) {
      nextFetch = () => Promise.reject(error);
      await assert.rejects(window.fetch("/api/auth/active-institution/"), (actual) => actual === error);
      await new Promise((resolve) => setImmediate(resolve));
    }
    assert.deepEqual(unhandled, []);
    assert.deepEqual(events, []);
    nextFetch = () => Promise.resolve({ status: 401 });
    assert.equal((await window.fetch("/api/finance/invoices/")).status, 401);
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(events, ["pf:unauthorized"]);
  } finally {
    process.removeListener("unhandledRejection", listener);
    globalThis.window = previousWindow;
    globalThis.CustomEvent = previousEvent;
  }
});
