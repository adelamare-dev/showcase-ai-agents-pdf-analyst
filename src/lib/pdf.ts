/** Characters of PDF text sent to the agent. Longer documents are cut at a
 *  page boundary so the model never receives half a page. */
export const PDF_TEXT_MAX_CHARS = 60_000;

/** Pages read at most. A PDF without a text layer (a scan) never raises the
 *  running character total, so the text cap cannot stop the read: only this
 *  limit keeps a document of thousands of pages from freezing the tab. */
export const PDF_MAX_PAGES = 1_000;

export type LoadedPdf = {
  filename: string;
  pages: number;
  keptPages: number;
  truncated: boolean;
  chars: number;
};

/** Client-side PDF → text extraction. pdfjs is imported lazily so the page
 *  bundle stays small and this module stays importable from Node tests. */
export async function extractPdfText(file: File): Promise<{
  pageTexts: string[];
  pages: number;
}> {
  const buf = await file.arrayBuffer();
  // @ts-expect-error pdfjs ships its own types via a custom export
  const pdfjs = await import("pdfjs-dist/build/pdf.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/build/pdf.worker.min.mjs",
    import.meta.url,
  ).toString();
  // The PDF is untrusted: never let pdf.js compile code from it.
  const task = pdfjs.getDocument({ data: buf, isEvalSupported: false });
  return readThenDestroy(task, async (doc: PageSource) => {
    const pageTexts = await collectPageTexts(
      doc,
      PDF_TEXT_MAX_CHARS,
      PDF_MAX_PAGES,
    );
    return { pageTexts, pages: doc.numPages };
  });
}

/** Runs `read` on the document a pdf.js loading task produces, then destroys
 *  the task. Each task owns a worker that only `task.destroy()` ends, and it
 *  also destroys the document. The task is destroyed even when loading
 *  rejects (corrupt or password-protected PDF), and a failing `destroy` never
 *  replaces the error that came first. */
export async function readThenDestroy<D, T>(
  task: { promise: Promise<D>; destroy(): Promise<void> },
  read: (doc: D) => Promise<T>,
): Promise<T> {
  try {
    return await read(await task.promise);
  } finally {
    await task.destroy().catch(() => {});
  }
}

/** The part of a pdf.js text item that layout needs. */
export type PdfTextItem = {
  str?: string;
  transform?: number[];
  width?: number;
  height?: number;
};

/** The part of a pdf.js document that page reading needs. */
type PageSource = {
  numPages: number;
  getPage(p: number): Promise<{
    getViewport(opts: { scale: number }): { width: number; rotation?: number };
    getTextContent(): Promise<{ items: PdfTextItem[] }>;
  }>;
};

// pdf.js emits text in the order the PDF draws it, which is not reading order:
// a table header can come after every row of values, so no model can match
// columns to their labels. Items are therefore regrouped by position. Pages
// laid out in several columns keep the stream order, because sorting by line
// would interleave the columns.

/** Baseline tolerance for items without a usable height. Others share a line
 *  when they overlap vertically by half the smaller height, so a superscript
 *  stays on its line and a large title does not swallow its subtitle. */
const LINE_MIN_TOLERANCE = 3;
/** Neighbouring items closer than one text height form a single cell. */
const CELL_GAP_IN_HEIGHTS = 1;
/** Inside a cell, a gap above this share of the height is a space; a smaller
 *  one glues ligatures and split glyphs back together. */
const SPACE_GAP_IN_HEIGHTS = 0.1;
/** A cell this wide (share of the page width) counts as running text. */
const WIDE_CELL_SHARE = 0.25;
/** A page is multi-column when this share of its wide cells starts in the
 *  right half. */
const RIGHT_HALF_SHARE = 0.25;
/** So is a page with this many lines holding two wide cells side by side: part
 *  of it is in columns, even if full-width text dominates the share above. */
const SIDE_BY_SIDE_LINES = 2;

type Placed = {
  str: string;
  x: number;
  y: number;
  w: number;
  h: number;
  spaceBefore: boolean;
  spaceAfter: boolean;
};
type Row = { top: number; bottom: number; items: Placed[] };
type Cell = { start: number; end: number; text: string; spaceAfter: boolean };

function sharesLine(row: Row, it: Placed): boolean {
  const smaller = Math.min(row.top - row.bottom, it.h);
  if (smaller <= 0) return Math.abs(row.bottom - it.y) <= LINE_MIN_TOLERANCE;
  const overlap = Math.min(row.top, it.y + it.h) - Math.max(row.bottom, it.y);
  return overlap >= smaller / 2;
}

function streamOrderText(items: PdfTextItem[]): string {
  return items
    .map((it) => it.str ?? "")
    .filter(Boolean)
    .join(" ");
}

/** Rebuilds the text of a page from its items and their positions: one line
 *  of text per line of the page, top to bottom, cells joined with " | ", then
 *  any vertical text (axis titles) on lines of its own. Falls back to the stream
 *  order when an item has no coordinates, when the page width is unknown, when
 *  most of the text is vertical, or when the page is laid out in several
 *  columns. */
export function pageTextFromItems(
  items: PdfTextItem[],
  pageWidth: number,
): string {
  if (!(pageWidth > 0)) return streamOrderText(items);
  const placed: Placed[] = [];
  const vertical: string[] = [];
  for (const it of items) {
    const raw = it.str ?? "";
    const str = raw.trim();
    if (!str) continue;
    const t = it.transform;
    if (!t || !Number.isFinite(t[4]) || !Number.isFinite(t[5])) {
      return streamOrderText(items);
    }
    if (Math.abs(t[1]) > Math.abs(t[0])) {
      vertical.push(str);
      continue;
    }
    placed.push({
      str,
      x: t[4],
      y: t[5],
      w: it.width ?? 0,
      h: it.height ?? 0,
      spaceBefore: /^\s/.test(raw),
      spaceAfter: /\s$/.test(raw),
    });
  }
  if (vertical.length > placed.length) return streamOrderText(items);

  // Sorted first so each item is compared to the current line only: a crafted
  // page can hold a huge number of items, and the extraction runs in the tab.
  const rows: Row[] = [];
  for (const it of placed.slice().sort((a, b) => b.y - a.y)) {
    const row = rows.at(-1);
    if (row && sharesLine(row, it)) {
      row.items.push(it);
      row.top = Math.max(row.top, it.y + it.h);
      row.bottom = Math.min(row.bottom, it.y);
    } else {
      rows.push({ top: it.y + it.h, bottom: it.y, items: [it] });
    }
  }

  const lines = rows.map((row) => {
    const cells: Cell[] = [];
    for (const it of row.items.slice().sort((a, b) => a.x - b.x)) {
      const last = cells.at(-1);
      const gap = last ? it.x - last.end : 0;
      if (last && gap < it.h * CELL_GAP_IN_HEIGHTS) {
        const spaced =
          last.spaceAfter ||
          it.spaceBefore ||
          gap > it.h * SPACE_GAP_IN_HEIGHTS;
        last.text += (spaced ? " " : "") + it.str;
        last.end = Math.max(last.end, it.x + it.w);
        last.spaceAfter = it.spaceAfter;
      } else {
        cells.push({
          start: it.x,
          end: it.x + it.w,
          text: it.str,
          spaceAfter: it.spaceAfter,
        });
      }
    }
    return cells;
  });

  const isWide = (c: Cell) => c.end - c.start >= pageWidth * WIDE_CELL_SHARE;
  const wide = lines.flat().filter(isWide);
  const right = wide.filter((c) => c.start >= pageWidth / 2).length;
  const sideBySide = lines.filter(
    (cells) => cells.filter(isWide).length >= 2,
  ).length;
  if (
    (wide.length > 0 && right / wide.length >= RIGHT_HALF_SHARE) ||
    sideBySide >= SIDE_BY_SIDE_LINES
  ) {
    return streamOrderText(items);
  }
  return [
    ...lines.map((cells) => cells.map((c) => c.text).join(" | ")),
    ...vertical,
  ].join("\n");
}

/** Reads page texts in order and stops as soon as the running total (pages
 *  joined with "\n", as `capPages` does) exceeds `maxChars`, or after
 *  `maxPages` pages. The page that crosses the cap is kept so `capPages` can
 *  tell the text was cut. */
export async function collectPageTexts(
  doc: PageSource,
  maxChars: number,
  maxPages: number,
): Promise<string[]> {
  const pageTexts: string[] = [];
  const last = Math.min(doc.numPages, maxPages);
  let total = 0;
  for (let p = 1; p <= last; p++) {
    const page = await doc.getPage(p);
    const content = await page.getTextContent();
    const { width, rotation } = page.getViewport({ scale: 1 });
    // On a rotated page, coordinates are those of the page before rotation.
    const text = rotation
      ? streamOrderText(content.items)
      : pageTextFromItems(content.items, width);
    pageTexts.push(text);
    total += (p === 1 ? 0 : 1) + text.length;
    if (total > maxChars) break;
  }
  return pageTexts;
}

/** True when the document is only partly represented: either `capPages` cut
 *  the text, or reading stopped before the last page (page limit) while the
 *  text that was read still fit. */
export function isPartialRead(
  capTruncated: boolean,
  readPages: number,
  totalPages: number,
): boolean {
  return capTruncated || readPages < totalPages;
}

/** Joins pages with "\n" and keeps whole pages while the total stays within
 *  `maxChars`. If page 1 alone is too long, it is cut at `maxChars`. */
export function capPages(
  pageTexts: string[],
  maxChars: number,
): { text: string; keptPages: number; truncated: boolean } {
  let text = "";
  let keptPages = 0;
  for (const page of pageTexts) {
    const next = keptPages === 0 ? page : `${text}\n${page}`;
    if (next.length > maxChars) break;
    text = next;
    keptPages++;
  }
  if (keptPages === 0 && pageTexts.length > 0) {
    return {
      text: pageTexts[0].slice(0, maxChars),
      keptPages: 1,
      truncated: true,
    };
  }
  return { text, keptPages, truncated: keptPages < pageTexts.length };
}

export function truncationNote(keptPages: number, totalPages: number): string {
  return `Document tronqué : pages 1 à ${keptPages} sur ${totalPages}`;
}

/** A PDF that parsed but holds nothing the agent could read. Its message is
 *  meant for the user, unlike the errors thrown by the PDF parser. */
export class NoTextError extends Error {
  constructor() {
    super("Aucun texte extractible dans ce PDF (document scanné ?).");
    this.name = "NoTextError";
  }
}

/** Single extraction path: extracts, caps, and prefixes the value with the
 *  truncation note when pages were dropped so the agent knows it is partial. */
export async function preparePdf(
  file: File,
): Promise<{ value: string; loaded: LoadedPdf }> {
  const { pageTexts, pages } = await extractPdfText(file);
  const capped = capPages(pageTexts, PDF_TEXT_MAX_CHARS);
  const { text, keptPages } = capped;
  if (text.trim() === "") {
    throw new NoTextError();
  }
  const truncated = isPartialRead(capped.truncated, pageTexts.length, pages);
  const value = truncated
    ? `[${truncationNote(keptPages, pages)}]\n${text}`
    : text;
  return {
    value,
    loaded: {
      filename: file.name,
      pages,
      keptPages,
      truncated,
      chars: text.length,
    },
  };
}
