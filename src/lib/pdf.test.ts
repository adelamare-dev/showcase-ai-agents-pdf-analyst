import { test } from "node:test";
import assert from "node:assert/strict";
import {
  capPages,
  collectPageTexts,
  isPartialRead,
  PDF_MAX_PAGES,
  pageTextFromItems,
  readThenDestroy,
  truncationNote,
  type PdfTextItem,
} from "./pdf.ts";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

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
      return {
        getViewport: () => ({ width: 612 }),
        getTextContent: async () => ({ items: [{ str }] }),
      };
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

/** Text item at (x, y) with a width of 5 per character. */
function at(str: string, x: number, y: number, height = 10): PdfTextItem {
  return { str, transform: [1, 0, 0, 1, x, y], width: str.length * 5, height };
}

test("pageTextFromItems puts a header emitted after its rows back on top", () => {
  const items = [
    at("PIB", 50, 390),
    at("0,4", 260, 390),
    at("0,3", 300, 390),
    at("2025T3", 260, 405),
    at("2025T4", 300, 405),
  ];
  assert.equal(pageTextFromItems(items, 612), "2025T3 | 2025T4\nPIB | 0,4 | 0,3");
});

test("pageTextFromItems keeps a space carried inside an item", () => {
  // Word and LibreOffice exports put the space in the item, its width included.
  const items = [at("Chiffre ", 50, 100), at("d'affaires", 90, 100)];
  assert.equal(pageTextFromItems(items, 612), "Chiffre d'affaires");
});

test("pageTextFromItems keeps a large title and its subtitle on two lines", () => {
  const items = [at("Titre", 50, 700, 24), at("Sous-titre", 50, 688, 12)];
  assert.equal(pageTextFromItems(items, 612), "Titre\nSous-titre");
});

test("pageTextFromItems sets vertical text apart from the rows", () => {
  const axis = { str: "Axe", transform: [0, 1, -1, 0, 10, 100], width: 15, height: 8 };
  const items = [at("Total", 50, 100), axis, at("12", 300, 100)];
  assert.equal(pageTextFromItems(items, 612), "Total | 12\nAxe");
});

test("pageTextFromItems keeps the stream order on a mostly vertical page", () => {
  const vertical = (str: string, x: number) => ({
    str,
    transform: [0, 1, -1, 0, x, 100],
    width: 15,
    height: 8,
  });
  const items = [vertical("b", 80), at("c", 50, 100), vertical("a", 10)];
  assert.equal(pageTextFromItems(items, 612), "b c a");
});

test("pageTextFromItems keeps the stream order on a page mixing layouts", () => {
  const items = [
    ...Array.from({ length: 20 }, (_, i) => at("F".repeat(100), 50, 700 - i * 14)),
    ...[400, 386, 372].flatMap((y) => [
      at("R".repeat(40), 320, y),
      at("L".repeat(40), 60, y),
    ]),
  ];
  const flow = items.map((i) => i.str).join(" ");
  assert.equal(pageTextFromItems(items, 612), flow);
});

test("collectPageTexts keeps the stream order on a rotated page", async () => {
  const doc = {
    numPages: 1,
    getPage: async () => ({
      getViewport: () => ({ width: 842, rotation: 90 }),
      getTextContent: async () => ({
        items: [at("b", 50, 100), at("a", 50, 200)],
      }),
    }),
  };
  assert.deepEqual(await collectPageTexts(doc, 1000, 10), ["b a"]);
});

test("pageTextFromItems stays fast on a page crafted with many lines", () => {
  const items = Array.from({ length: 100_000 }, (_, i) => at("x", 50, i * 20));
  const start = performance.now();
  pageTextFromItems(items, 612);
  assert.ok(performance.now() - start < 5_000);
});

test("pageTextFromItems separates distant cells with a pipe", () => {
  const items = [at("Total", 50, 100), at("12", 300, 100)];
  assert.equal(pageTextFromItems(items, 612), "Total | 12");
});

test("pageTextFromItems merges close words with a space", () => {
  // "Demande" ends at x=85; "intérieure" starts 4 later, under the cell gap.
  const items = [at("Demande", 50, 100), at("intérieure", 89, 100)];
  assert.equal(pageTextFromItems(items, 612), "Demande intérieure");
});

test("pageTextFromItems glues a ligature without a space", () => {
  // "ﬁ" ends at x=55 and "nale" starts right there: no gap, no space.
  const items = [at("\ufb01", 50, 100), at("nale", 55, 100)];
  assert.equal(pageTextFromItems(items, 612), "\ufb01nale");
});

test("pageTextFromItems keeps a superscript on its line", () => {
  const items = [at("m", 50, 100), at("2", 55, 104, 6)];
  assert.equal(pageTextFromItems(items, 612), "m2");
});

test("pageTextFromItems ignores blank items", () => {
  const items = [at("  ", 50, 200), at("", 80, 200), at("a", 50, 100)];
  assert.equal(pageTextFromItems(items, 612), "a");
});

test("pageTextFromItems keeps the stream order on a two-column page", () => {
  const items = [
    at("L".repeat(40), 60, 700),
    at("R".repeat(40), 320, 700),
    at("L".repeat(40), 60, 686),
    at("R".repeat(40), 320, 686),
  ].sort((a, b) => b.transform![4] - a.transform![4]);
  const flow = items.map((i) => i.str).join(" ");
  assert.equal(pageTextFromItems(items, 612), flow);
});

test("pageTextFromItems keeps the stream order without coordinates", () => {
  const items: PdfTextItem[] = [{ str: "b" }, { str: "" }, { str: "a" }];
  assert.equal(pageTextFromItems(items, 612), "b a");
  const mixed = [at("z", 10, 10), { str: "y" }];
  assert.equal(pageTextFromItems(mixed, 612), "z y");
});

test("pageTextFromItems keeps the stream order when the page width is unknown", () => {
  const items = [at("b", 50, 100), at("a", 50, 200)];
  assert.equal(pageTextFromItems(items, 0), "b a");
});

/** Loads a sample PDF with the real pdf.js and returns, per page, the
 *  extracted text and the stream-order join of its items. */
async function readSample(name: string) {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const data = new Uint8Array(
    readFileSync(
      fileURLToPath(new URL(`../../public/samples/${name}`, import.meta.url)),
    ),
  );
  const doc = await pdfjs.getDocument({ data, isEvalSupported: false }).promise;
  try {
    const pages: { text: string; flow: string }[] = [];
    for (let p = 1; p <= doc.numPages; p++) {
      const page = await doc.getPage(p);
      const items = (await page.getTextContent()).items as PdfTextItem[];
      const width = page.getViewport({ scale: 1 }).width;
      pages.push({
        text: pageTextFromItems(items, width),
        flow: items
          .map((it) => it.str ?? "")
          .filter(Boolean)
          .join(" "),
      });
    }
    return pages;
  } finally {
    await doc.destroy();
  }
}

test("Insee sample: the table header sits right above the PIB row", async () => {
  const pages = await readSample("insee-comptes-nationaux-t2-2026.pdf");
  const lines = pages.flatMap((p) => p.text.split("\n"));
  const header = lines.indexOf("2025T3 | 2025T4 | 2026T1 | 2026T2 | 2025 | 2026 (acquis)");
  assert.notEqual(header, -1);
  assert.equal(lines[header + 1], "PIB | 0,4 | 0,3 | -0,2 | 0,0 | 0,9 | 0,3");
});

test("arXiv sample: two-column pages keep the stream order", async () => {
  const pages = await readSample("arxiv-2610.07204-spear.pdf");
  for (const p of pages) assert.equal(p.text, p.flow);
});
