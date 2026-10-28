"use client";

import { useMemo, useState, type ComponentProps } from "react";
import type { CopilotChat } from "@copilotkit/react-core/v2";
import { preparePdf, type LoadedPdf } from "@/lib/pdf";

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
  const [loaded, setLoaded] = useState<LoadedPdf | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const attachments = useMemo<Attachments>(
    () => ({
      enabled: true,
      accept: "application/pdf",
      maxSize: 20 * 1024 * 1024,
      onUpload: async (file) => {
        setUploadError(null);
        const { value, loaded: pdf } = await preparePdf(file);
        setLoaded(pdf);
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
      onUploadFailed: (err) => setUploadError(err.message),
    }),
    [],
  );

  return { loaded, uploadError, setLoaded, attachments };
}
