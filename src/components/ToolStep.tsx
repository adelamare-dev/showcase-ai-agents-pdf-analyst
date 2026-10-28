"use client";

import { z } from "zod";
import { useRenderTool } from "@copilotkit/react-core/v2";
import { TOOL_STEPS, type StepTool } from "@/lib/agent-steps";

type StepStatus = "inProgress" | "executing" | "complete";

/* One chat line per tool call. Never shows the call's parameters or result:
 * query_pdf arguments and results can carry document text. */
export function ToolStep({
  tool,
  status,
}: {
  tool: StepTool;
  status: StepStatus;
}) {
  const step = TOOL_STEPS[tool];
  const complete = status === "complete";
  return (
    <div className="surface-soft px-3 py-2 my-1 flex items-center gap-3 text-[13px] text-[var(--ink-2)]">
      {complete ? (
        <span aria-hidden className="text-[var(--ink)]">
          ✓
        </span>
      ) : status === "executing" ? (
        <span className="relative inline-flex h-2.5 w-2.5" aria-hidden>
          <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--lilac)] opacity-75 animate-ping" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[var(--lilac)]" />
        </span>
      ) : (
        <span
          aria-hidden
          className="inline-flex rounded-full h-2.5 w-2.5 bg-[var(--ink-2)] opacity-50 animate-pulse"
        />
      )}
      <span>{complete ? step.done : step.running}</span>
      <span className="ml-auto text-[11px] opacity-80">{step.model}</span>
    </div>
  );
}

/* Registers a step renderer for every tool of both agents. A renderer for a
 * tool the active agent never calls is inert. */
export function useToolStepRenderers(): void {
  useRenderTool({
    name: "query_pdf",
    parameters: z.any(),
    render: ({ status }) => <ToolStep tool="query_pdf" status={status} />,
  });
  useRenderTool({
    name: "generate_a2ui",
    parameters: z.any(),
    render: ({ status }) => <ToolStep tool="generate_a2ui" status={status} />,
  });
  useRenderTool({
    name: "render_dashboard",
    parameters: z.any(),
    render: ({ status }) => (
      <ToolStep tool="render_dashboard" status={status} />
    ),
  });
}
