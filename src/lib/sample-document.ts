/* No runtime import: Node runs this file directly in the unit tests. */
import type { InputContentPart, Message } from "@ag-ui/core";
import type { LoadedPdf } from "./pdf.ts";

export type SampleDocument = { value: string; loaded: LoadedPdf };

type DocumentPart = Extract<InputContentPart, { type: "document" }>;

/** The `document` part in the shape the composer produces for an uploaded PDF. */
export function documentPart({ value, loaded }: SampleDocument): DocumentPart {
  return {
    type: "document",
    source: { type: "data", value, mimeType: "text/plain" },
    metadata: {
      filename: loaded.filename,
      pages: loaded.pages,
      originalMime: "application/pdf",
    },
  };
}

/** Attaches the document to the only user message of the thread. Returns `null`
 *  when there is nothing to do: the thread holds no user message or more than
 *  one (the sample bar only shows on an empty thread, and once a run has ended
 *  the thread carries the document as `[Document: ...]` text), or that message
 *  already has a `document` part (an upload through the composer wins). The
 *  input is not mutated. */
export function withSampleDocument(
  messages: readonly Message[],
  doc: SampleDocument,
): Message[] | null {
  const users = messages.filter((m) => m.role === "user");
  if (users.length !== 1) return null;
  const target = users[0];
  if (target.role !== "user") return null;
  if (
    Array.isArray(target.content) &&
    target.content.some((part) => part.type === "document")
  ) {
    return null;
  }
  const parts: InputContentPart[] =
    typeof target.content === "string"
      ? [{ type: "text", text: target.content }]
      : target.content;
  return messages.map((m) =>
    m === target ? { ...target, content: [...parts, documentPart(doc)] } : m,
  );
}
