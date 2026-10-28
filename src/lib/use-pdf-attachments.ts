"use client";

import { useCallback, useMemo, useState, type ComponentProps } from "react";
import type { CopilotChat } from "@copilotkit/react-core/v2";
import { NoTextError, preparePdf, type LoadedPdf } from "@/lib/pdf";
import { uploadErrorMessage } from "@/lib/upload-errors";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

type Attachments = NonNullable<
  ComponentProps<typeof CopilotChat>["attachments"]
>;

/** Shared PDF upload config for the chat pages. An error thrown by
 *  `onUpload` is reported by CopilotKit through `onUploadFailed` (the
 *  attachment is dropped and nothing is sent) and surfaces as `uploadError`. */
export function usePdfAttachments(): {
  loaded: LoadedPdf | null;
  uploadError: string | null;
  setLoaded: (pdf: LoadedPdf) => void;
  attachments: Attachments;
} {
  const [loaded, setLoadedState] = useState<LoadedPdf | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const setLoaded = useCallback((pdf: LoadedPdf) => {
    setUploadError(null);
    setLoadedState(pdf);
  }, []);

  const attachments = useMemo<Attachments>(
    () => ({
      enabled: true,
      accept: "application/pdf",
      maxSize: MAX_UPLOAD_BYTES,
      onUpload: async (file) => {
        setUploadError(null);
        let prepared: Awaited<ReturnType<typeof preparePdf>>;
        try {
          prepared = await preparePdf(file);
        } catch (err) {
          // Parser errors are English and technical: keep them in the console
          // and let CopilotKit report a generic French failure.
          if (err instanceof NoTextError) throw err;
          console.error("PDF extraction failed", err);
          throw new Error(
            uploadErrorMessage(
              { reason: "upload-failed", file, message: "" },
              MAX_UPLOAD_BYTES,
            ),
          );
        }
        const { value, loaded: pdf } = prepared;
        setLoadedState(pdf);
        return {
          type: "data",
          value,
          mimeType: "text/plain",
          metadata: {
            filename: file.name,
            pages: pdf.pages,
            originalMime: "application/pdf",
          },
        };
      },
      onUploadFailed: (failure) =>
        setUploadError(
          failure.reason === "upload-failed"
            ? failure.message
            : uploadErrorMessage(failure, MAX_UPLOAD_BYTES),
        ),
    }),
    [],
  );

  return { loaded, uploadError, setLoaded, attachments };
}
