/** Characters of PDF text sent to the agent. Longer documents are cut at a
 *  page boundary so the model never receives half a page. */
export const PDF_TEXT_MAX_CHARS = 60_000;

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
  pdfjs.GlobalWorkerOptions.workerSrc =
    "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs";
  // The PDF is untrusted: never let pdf.js compile code from it.
  const doc = await pdfjs.getDocument({ data: buf, isEvalSupported: false })
    .promise;
  const pageTexts: string[] = [];
  for (let p = 1; p <= doc.numPages; p++) {
    const page = await doc.getPage(p);
    const content = await page.getTextContent();
    pageTexts.push(
      content.items
        .map((it: { str?: string }) => it.str ?? "")
        .filter(Boolean)
        .join(" "),
    );
  }
  return { pageTexts, pages: doc.numPages };
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
  const { text, keptPages, truncated } = capPages(
    pageTexts,
    PDF_TEXT_MAX_CHARS,
  );
  if (text.trim() === "") {
    throw new NoTextError();
  }
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
