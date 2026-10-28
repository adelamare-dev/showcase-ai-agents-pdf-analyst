"use client";

import { CopilotChat, useAgent } from "@copilotkit/react-core/v2";
import { SiteNav } from "@/components/Brand";
import { SurfaceCanvas, CanvasEmptyState } from "@/components/SurfaceCanvas";
import { FilteredUserMessage } from "@/components/FilteredUserMessage";
import { FilteredAssistantMessage } from "@/components/FilteredAssistantMessage";
import { useToolStepRenderers } from "@/components/ToolStep";
import { Split } from "@/components/Split";
import { SampleBar } from "@/components/SampleBar";
import { SAMPLES } from "@/lib/samples";
import { CHAT_LABELS } from "@/lib/chat-labels";
import { usePdfAttachments } from "@/lib/use-pdf-attachments";
import {
  PdfStatusBar,
  ConfidentialityNotice,
} from "@/components/PdfChatChrome";

const AGENT_ID = "dynamic_agent";

export default function DynamicPage() {
  useAgent({ agentId: AGENT_ID });
  const { loaded, uploadError, setLoaded, attachments } = usePdfAttachments();

  useToolStepRenderers();

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
                  ...CHAT_LABELS,
                  chatInputPlaceholder: "Posez une question sur le PDF…",
                  welcomeMessageText:
                    "Joignez un PDF avec le bouton 📎, puis posez n’importe quelle question.",
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
                title="Le canevas est vide"
                subtitle="Joignez un PDF dans la discussion et posez votre question. L’agent compose une surface à partir du catalogue et l’affiche ici."
                hint={
                  <span className="mono text-[11px] uppercase tracking-[0.14em] text-[var(--ink)]">
                    essayez : « Montre-moi l’évolution du chiffre d’affaires. »
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
