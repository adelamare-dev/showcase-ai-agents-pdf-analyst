/**
 * Chat labels for each agent tool call. The `model` strings duplicate the
 * display names of the model roles configured in `agent/src/models.py`:
 * change both together.
 */
export const TOOL_STEPS = {
  query_pdf: {
    running: "Lecture du document…",
    done: "Document lu",
    model: "Ministral 3B",
  },
  generate_a2ui: {
    running: "Conception de l'interface…",
    done: "Interface conçue",
    model: "Ministral 8B",
  },
  render_dashboard: {
    running: "Construction du tableau de bord…",
    done: "Tableau de bord prêt",
    model: "Ministral 3B",
  },
} as const;

export type StepTool = keyof typeof TOOL_STEPS;
