import { test } from "node:test";
import assert from "node:assert/strict";
import {
  capPages,
  collectPageTexts,
  isPartialRead,
  PDF_MAX_PAGES,
  readThenDestroy,
  truncationNote,
} from "./pdf.ts";

/** Fake pdf.js loading task: `destroys` counts the `destroy` calls. */
function fakeTask<D>(opts: {
  doc?: D;
  loadError?: Error;
  destroyError?: Error;
}) {
  const task = {
    destroys: 0,
    promise: opts.loadError
      ? Promise.reject(opts.loadError)
      : Promise.resolve(opts.doc as D),
    async destroy() {
      task.destroys++;
      if (opts.destroyError) throw opts.destroyError;
    },
  };
  task.promise.catch(() => {});
  return task;
}

test("readThenDestroy destroys the task when loading rejects", async () => {
  const task = fakeTask({ loadError: new Error("password") });
  await assert.rejects(
    readThenDestroy(task, async () => "never"),
    /password/,
  );
  assert.equal(task.destroys, 1);
});

test("readThenDestroy destroys the task when reading fails", async () => {
  const task = fakeTask({ doc: {} });
  await assert.rejects(
    readThenDestroy(task, async () => {
      throw new Error("bad page");
    }),
    /bad page/,
  );
  assert.equal(task.destroys, 1);
});

test("readThenDestroy keeps the original error when destroy also rejects", async () => {
  const task = fakeTask({ doc: {}, destroyError: new Error("destroy failed") });
  await assert.rejects(
    readThenDestroy(task, async () => {
      throw new Error("bad page");
    }),
    /bad page/,
  );
  assert.equal(task.destroys, 1);
});

test("readThenDestroy returns the result and destroys the task", async () => {
  const task = fakeTask({ doc: { n: 7 } });
  const result = await readThenDestroy(task, async (doc) => doc.n);
  assert.equal(result, 7);
  assert.equal(task.destroys, 1);
});

/** Fake pdf.js document: every page holds `texts[i]` (or "" past the end of
 *  `texts`) and `reads` counts the `getPage` calls. */
function fakeDoc(numPages: number, texts: string[] = []) {
  const doc = {
    numPages,
    reads: 0,
    async getPage(p: number) {
      doc.reads++;
      const str = texts[p - 1] ?? "";
      return { getTextContent: async () => ({ items: [{ str }] }) };
    },
  };
  return doc;
}

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

test("collectPageTexts reads a small document in full", async () => {
  const doc = fakeDoc(3, ["aaa", "bbb", "ccc"]);
  assert.deepEqual(await collectPageTexts(doc, 100, 1_000), [
    "aaa",
    "bbb",
    "ccc",
  ]);
  assert.equal(doc.reads, 3);
});

test("collectPageTexts stops right after the page that exceeds the cap", async () => {
  const page = "p".repeat(40);
  const doc = fakeDoc(500, Array(500).fill(page));
  const pageTexts = await collectPageTexts(doc, 90, 1_000);
  // 40 + 1 + 40 = 81 fits, the third page brings the total to 122 > 90.
  assert.equal(pageTexts.length, 3);
  assert.equal(doc.reads, 3);
  // capPages still sees the overflow page and reports the truncation.
  const capped = capPages(pageTexts, 90);
  assert.equal(capped.keptPages, 2);
  assert.equal(capped.truncated, true);
});

test("collectPageTexts stops at the page limit on a document without text", async () => {
  const doc = fakeDoc(5_000);
  const pageTexts = await collectPageTexts(doc, 60_000, 10);
  assert.equal(pageTexts.length, 10);
  assert.equal(doc.reads, 10);
});

test("PDF_MAX_PAGES is a positive page count", () => {
  assert.ok(Number.isInteger(PDF_MAX_PAGES) && PDF_MAX_PAGES > 0);
});

test("isPartialRead flags pages left unread even when the text fits", () => {
  const capped = capPages(["aaa", "bbb"], 100);
  assert.equal(capped.truncated, false);
  assert.equal(isPartialRead(capped.truncated, 2, 5_000), true);
  assert.equal(isPartialRead(capped.truncated, 2, 2), false);
  assert.equal(isPartialRead(true, 2, 2), true);
});

test("truncationNote formats the French label", () => {
  assert.equal(truncationNote(3, 12), "Document tronqué : pages 1 à 3 sur 12");
});
