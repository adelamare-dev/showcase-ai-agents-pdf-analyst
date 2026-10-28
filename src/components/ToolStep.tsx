"use client";

import { z } from "zod";
import { useRenderTool } from "@copilotkit/react-core/v2";
import { TOOL_STEPS, isToolFailure, type StepTool } from "@/lib/agent-steps";

type StepStatus = "inProgress" | "executing" | "complete";

/* One chat line per tool call. Never shows the call's parameters or the result text:
 * query_pdf arguments and results can carry document text. */
export function ToolStep({
  tool,
  status,
  result,
}: {
  tool: StepTool;
  status: StepStatus;
  result?: unknown;
}) {
  const step = TOOL_STEPS[tool];
  const complete = status === "complete";
  const failed = complete && isToolFailure(result);
  return (
    <div
      role="status"
      className="surface-soft px-3 py-2 my-1 flex items-center gap-3 text-[13px] text-[var(--ink-2)]">
      {failed ? (
        <span aria-hidden className="text-[var(--red)]">
          ✕
        </span>
      ) : complete ? (
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
      <span>{failed ? step.failed : complete ? step.done : step.running}</span>
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
    render: ({ status, result }) => (
      <ToolStep tool="query_pdf" status={status} result={result} />
    ),
  });
  useRenderTool({
    name: "generate_a2ui",
    parameters: z.any(),
    render: ({ status, result }) => (
      <ToolStep tool="generate_a2ui" status={status} result={result} />
    ),
  });
  useRenderTool({
    name: "render_dashboard",
    parameters: z.any(),
    render: ({ status, result }) => (
      <ToolStep tool="render_dashboard" status={status} result={result} />
    ),
  });
}
