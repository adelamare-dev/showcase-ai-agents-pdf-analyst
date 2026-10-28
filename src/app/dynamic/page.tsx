"use client";

import { z } from "zod";
import {
  CopilotChat,
  useAgent,
  useRenderTool,
} from "@copilotkit/react-core/v2";
import { SiteNav } from "@/components/Brand";
import { SurfaceCanvas, CanvasEmptyState } from "@/components/SurfaceCanvas";
import { FilteredUserMessage } from "@/components/FilteredUserMessage";
import { FilteredAssistantMessage } from "@/components/FilteredAssistantMessage";
import { Split } from "@/components/Split";
import { SampleBar } from "@/components/SampleBar";
import { SAMPLES } from "@/lib/samples";
import { usePdfAttachments } from "@/lib/use-pdf-attachments";
import {
  PdfStatusBar,
  ConfidentialityNotice,
} from "@/components/PdfChatChrome";

const AGENT_ID = "dynamic_agent";

export default function DynamicPage() {
  useAgent({ agentId: AGENT_ID });
  const { loaded, uploadError, setLoaded, attachments } = usePdfAttachments();

  // generate_a2ui (the Python tool) is now the surface producer. Show a
  // small pill while it streams, hide on complete (the rendered surface
  // appears in the canvas. chat doesn't need a record of it).
  useRenderTool({
    name: "generate_a2ui",
    parameters: z.any(),
    render: ({ status }) => {
      if (status === "complete") return <></>;
      return (
        <div className="surface-soft px-3 py-2 my-1 flex items-center gap-3 text-[13px] text-[var(--ink-2)]">
          <span className="relative inline-flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--lilac)] opacity-75 animate-ping" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[var(--lilac)]" />
          </span>
          <span>Composing a surface…</span>
        </div>
      );
    },
  });

  // query_pdf: render nothing, ever. The "Composing a surface…" pill
  // from generate_a2ui is the only chat signal we want. We override the
  // default tool card here (instead of leaving it) for two reasons:
  // 1) the default tool card keeps args/result in the DOM and our args
  //    are the full PDF body, which is noisy.
  // 2) when the agent calls query_pdf more than once per turn, the
  //    default would render multiple pills back to back.
  useRenderTool({
    name: "query_pdf",
    parameters: z.any(),
    render: () => <></>,
  });

  return (
    <div className="h-screen flex flex-col bg-[var(--bg)]">
      <SiteNav active="dynamic" />

      <Split
        persistKey="dynamic.split"
        initialLeftFraction={0.32}
        left={
          <div className="h-full flex flex-col copilot-chat-wrapper">
            <PdfStatusBar
              loaded={loaded}
              error={uploadError}
              accent="lilac"
            />
            <SampleBar
              agentId={AGENT_ID}
              samples={SAMPLES.dynamic}
              current={loaded}
              onLoaded={setLoaded}
            />
            <div className="flex-1 min-h-0">
              <CopilotChat
                agentId={AGENT_ID}
                chatView={{
                  messageView: {
                    userMessage: FilteredUserMessage,
                    assistantMessage: FilteredAssistantMessage,
                  },
                }}
                attachments={attachments}
                labels={{
                  chatInputPlaceholder: "Attach a PDF (📎), then ask anything…",
                  welcomeMessageText:
                    "Attach a PDF using the 📎 button, then ask any question.",
                }}
              />
            </div>
            <ConfidentialityNotice />
          </div>
        }
        right={
          <SurfaceCanvas
            channel={AGENT_ID}
            emptyState={
              <CanvasEmptyState
                title="Canvas is empty"
                subtitle="Attach a PDF in the chat and ask anything. The agent will compose a UI surface using the catalog and render it here."
                hint={
                  <span className="mono text-[11px] uppercase tracking-[0.14em] text-[var(--ink)]">
                    try: “Show me the revenue trend.”
                  </span>
                }
              />
            }
          />
        }
      />
    </div>
  );
}
