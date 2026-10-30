"use client";

import { useState } from "react";
import { useAgent, useCopilotKit } from "@copilotkit/react-core/v2";
import { preparePdf, type LoadedPdf } from "@/lib/pdf";
import type { Sample } from "@/lib/samples";

type Doc = { sample: Sample; value: string; loaded: LoadedPdf };

const BUTTON =
  "text-left text-[12px] px-2.5 py-1 rounded-md border border-[var(--line)] bg-[var(--surface)] text-[var(--ink)] hover:bg-[var(--bg)] disabled:opacity-50 disabled:cursor-not-allowed";

/** One-click sample documents, then clickable questions for the loaded one.
 *  The document is sent together with the clicked question as a single user
 *  message, in the same shape the composer produces for an uploaded PDF. */
export function SampleBar({
  agentId,
  samples,
  current,
  onLoaded,
}: {
  agentId: string;
  samples: Sample[];
  /** The document the page currently shows; a different one (composer upload) hides the suggestions. */
  current: LoadedPdf | null;
  onLoaded: (pdf: LoadedPdf) => void;
}) {
  // Until the runtime connection is up, `agent` is a placeholder private to this
  // component: a message sent on it runs, but the chat never shows it. Hence the
  // `isReady` guard on the suggestions.
  const { agent, isReady } = useAgent({ agentId });
  const { copilotkit } = useCopilotKit();
  const [doc, setDoc] = useState<Doc | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = agent.isRunning;
  const showSuggestions = doc !== null && doc.loaded === current;

  async function load(sample: Sample) {
    setError(null);
    try {
      const res = await fetch(`/samples/${sample.file}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const file = new File([blob], sample.file, { type: "application/pdf" });
      const { value, loaded } = await preparePdf(file);
      setDoc({ sample, value, loaded });
      onLoaded(loaded);
    } catch (err) {
      console.error("Sample load failed", err);
      setError("Impossible de charger cet exemple.");
    }
  }

  async function ask(question: string) {
    if (!doc || busy || !isReady) return;
    const { value, loaded } = doc;
    agent.addMessage({
      id: crypto.randomUUID(),
      role: "user",
      content: [
        { type: "text", text: question },
        {
          type: "document",
          source: { type: "data", value, mimeType: "text/plain" },
          metadata: {
            filename: loaded.filename,
            pages: loaded.pages,
            originalMime: "application/pdf",
          },
        },
      ],
    });
    try {
      await copilotkit.runAgent({ agent });
    } catch (err) {
      console.error("Agent run failed", err);
    }
  }

  if (agent.messages.length > 0) return null;

  return (
    <div className="shrink-0 px-4 py-2 border-b border-[var(--line)] flex flex-col gap-1.5">
      <span className="text-[11.5px] text-[var(--ink-2)]">
        Essayer un exemple :
      </span>
      <div className="flex flex-wrap gap-1.5">
        {samples.map((s) => (
          <button
            key={s.id}
            type="button"
            className={BUTTON}
            disabled={busy}
            onClick={() => void load(s)}
          >
            {s.label}
          </button>
        ))}
      </div>
      {error && (
        <p className="text-[11.5px] text-[#9b1c1c]" role="alert">
          {error}
        </p>
      )}
      {showSuggestions && (
        <div className="flex flex-col gap-1">
          {doc.sample.suggestions.map((q) => (
            <button
              key={q}
              type="button"
              className={BUTTON}
              disabled={busy || !isReady}
              onClick={() => void ask(q)}
            >
              {q}
            </button>
          ))}
          <span className="text-[11.5px] text-[var(--ink-2)]">
            Cliquez une question pour l&rsquo;envoyer avec le document.
          </span>
        </div>
      )}
    </div>
  );
}
