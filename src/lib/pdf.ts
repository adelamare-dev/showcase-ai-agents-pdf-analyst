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

/** The part of a pdf.js document that page reading needs. */
type PageSource = {
  numPages: number;
  getPage(p: number): Promise<{
    getTextContent(): Promise<{ items: Array<{ str?: string }> }>;
  }>;
};

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
    const text = content.items
      .map((it) => it.str ?? "")
      .filter(Boolean)
      .join(" ");
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
