import type { CopilotChatLabels } from "@copilotkit/react-core/v2";

/** French replacements for every `CopilotChatLabels` key, so no English
 *  default shows through. Pages add their own placeholder and welcome text. */
export const CHAT_LABELS: Partial<CopilotChatLabels> = {
  chatInputToolbarStartTranscribeButtonLabel: "Dicter",
  chatInputToolbarCancelTranscribeButtonLabel: "Annuler",
  chatInputToolbarFinishTranscribeButtonLabel: "Terminer",
  chatInputToolbarAddButtonLabel: "Ajouter des pièces jointes",
  chatInputToolbarToolsButtonLabel: "Outils",
  assistantMessageToolbarCopyCodeLabel: "Copier",
  assistantMessageToolbarCopyCodeCopiedLabel: "Copié",
  assistantMessageToolbarCopyMessageLabel: "Copier",
  assistantMessageToolbarThumbsUpLabel: "Bonne réponse",
  assistantMessageToolbarThumbsDownLabel: "Mauvaise réponse",
  assistantMessageToolbarReadAloudLabel: "Lire à voix haute",
  assistantMessageToolbarRegenerateLabel: "Régénérer",
  userMessageToolbarCopyMessageLabel: "Copier",
  userMessageToolbarEditMessageLabel: "Modifier",
  chatDisclaimerText:
    "L’IA peut se tromper. Vérifiez les informations importantes.",
  chatToggleOpenLabel: "Ouvrir la discussion",
  chatToggleCloseLabel: "Fermer la discussion",
  modalHeaderTitle: "Discussion CopilotKit",
};
