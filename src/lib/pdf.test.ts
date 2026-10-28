import { test } from "node:test";
import assert from "node:assert/strict";
import { capPages, truncationNote } from "./pdf.ts";

test("capPages keeps whole pages under the limit", () => {
  assert.deepEqual(capPages(["aaa", "bbb"], 100), {
    text: "aaa\nbbb",
    keptPages: 2,
    truncated: false,
  });
});

test("capPages cuts at a page boundary", () => {
  const page = "p".repeat(40);
  const r = capPages([page, page, page], 90);
  assert.equal(r.keptPages, 2);
  assert.equal(r.text.length, 81);
  assert.equal(r.truncated, true);
});

test("capPages keeps a truncated first page", () => {
  const r = capPages(["x".repeat(150)], 100);
  assert.equal(r.keptPages, 1);
  assert.equal(r.text.length, 100);
  assert.equal(r.truncated, true);
});

test("truncationNote formats the French label", () => {
  assert.equal(truncationNote(3, 12), "Document tronqué : pages 1 à 3 sur 12");
});
