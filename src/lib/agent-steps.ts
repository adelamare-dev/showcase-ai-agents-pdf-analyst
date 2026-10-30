/**
 * Chat labels for each agent tool call. The `model` strings duplicate the
 * display names of the model roles configured in `agent/src/models.py`:
 * change both together.
 *
 * `failed` is shown when the tool result carries the agent's provider-error
 * prefix (see `isToolFailure`).
 */
export const TOOL_STEPS = {
  query_pdf: {
    running: "Lecture du document…",
    done: "Document lu",
    failed: "Lecture du document interrompue",
    model: "Ministral 8B",
  },
  generate_a2ui: {
    running: "Conception de l'interface…",
    done: "Interface conçue",
    failed: "Conception de l'interface interrompue",
    model: "Ministral 8B",
  },
  render_dashboard: {
    running: "Construction du tableau de bord…",
    done: "Tableau de bord prêt",
    failed: "Tableau de bord interrompu",
    model: "Ministral 3B",
  },
} as const;

export type StepTool = keyof typeof TOOL_STEPS;

/** Prefix the agent's error middleware puts on a failed tool's result
 * (`TOOL_ERROR_PREFIX` in `agent/src/errors.py`): change both together. */
export const TOOL_ERROR_PREFIX = "MISTRAL_ERROR: ";

export function isToolFailure(result: unknown): boolean {
  return typeof result === "string" && result.startsWith(TOOL_ERROR_PREFIX);
}
