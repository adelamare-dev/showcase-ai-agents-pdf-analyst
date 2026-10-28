"use client";

import { CopilotChat, useAgent } from "@copilotkit/react-core/v2";
import { SiteNav } from "@/components/Brand";
import { SurfaceCanvas, CanvasEmptyState } from "@/components/SurfaceCanvas";
import { FilteredUserMessage } from "@/components/FilteredUserMessage";
import { FilteredAssistantMessage } from "@/components/FilteredAssistantMessage";
import { Split } from "@/components/Split";
import { usePdfAttachments } from "@/lib/use-pdf-attachments";
import {
  PdfStatusBar,
  ConfidentialityNotice,
} from "@/components/PdfChatChrome";

const AGENT_ID = "fixed_agent";

export default function FixedPage() {
  useAgent({ agentId: AGENT_ID });
  const { loaded, uploadError, attachments } = usePdfAttachments();

  return (
    <div className="h-screen flex flex-col bg-[var(--bg)]">
      <SiteNav active="fixed" />

      <Split
        persistKey="fixed.split"
        initialLeftFraction={0.32}
        left={
          <div className="h-full flex flex-col copilot-chat-wrapper">
            <PdfStatusBar
              loaded={loaded}
              error={uploadError}
              accent="mint"
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
                  chatInputPlaceholder:
                    "Attach a PDF (📎), then ask to render the dashboard…",
                  welcomeMessageText:
                    "Attach a PDF using the 📎 button, then ask: “Render the dashboard.”",
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
                subtitle="Attach a PDF in the chat (📎 in the input toolbar) and ask the agent to render the dashboard. The rendered A2UI surface will fill this canvas."
                hint={
                  <span className="mono text-[11px] uppercase tracking-[0.14em] text-[var(--ink)]">
                    try: “Render the dashboard.”
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
