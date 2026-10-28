import { truncationNote, type LoadedPdf } from "@/lib/pdf";

const ACCENT = {
  mint: { dot: "bg-[#0d6b4f]", tint: "var(--mint)" },
  lilac: { dot: "bg-[var(--lilac)]", tint: "var(--lilac)" },
} as const;

/** Status line above the chat: loaded PDF summary (with a truncation notice
 *  when pages were dropped) and/or the upload error. */
export function PdfStatusBar({
  loaded,
  error,
  accent,
}: {
  loaded: LoadedPdf | null;
  error: string | null;
  accent: "mint" | "lilac";
}) {
  if (!loaded && !error) return null;
  const { dot, tint } = ACCENT[accent];
  return (
    <div
      className="shrink-0 px-4 py-2 border-b border-[var(--line)] flex flex-col gap-1"
      style={{ background: `color-mix(in oklab, ${tint} 8%, var(--surface))` }}
    >
      {loaded && (
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
          <span className="mono text-[10.5px] uppercase tracking-[0.12em] text-[var(--ink)]">
            chargé
          </span>
          <span className="text-[12.5px] font-medium text-[var(--ink)] truncate min-w-0">
            {loaded.filename}
          </span>
          <span className="text-[11px] text-[var(--ink)] ml-auto shrink-0 whitespace-nowrap">
            {loaded.keptPages} / {loaded.pages} p. ·{" "}
            {Math.round(loaded.chars / 1000)}k car.
          </span>
        </div>
      )}
      {loaded?.truncated && (
        <p className="text-[11.5px] text-[var(--ink)]" role="status">
          {truncationNote(loaded.keptPages, loaded.pages)}
        </p>
      )}
      {error && (
        <p className="text-[11.5px] text-[#9b1c1c]" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

/** Confidentiality reminder shown under the composer. */
export function ConfidentialityNotice() {
  return (
    <p className="shrink-0 px-4 py-1.5 text-center text-[11px] text-[var(--ink-2)]">
      N&apos;envoyez pas de document confidentiel : démo sur l&apos;offre
      gratuite Mistral.
    </p>
  );
}
