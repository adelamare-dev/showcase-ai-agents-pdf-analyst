/* French wording for attachment rejections. CopilotKit reports a reason code
 * and an English message; only the code is relied on here. Kept import-free
 * so Node runs it directly in the unit tests. */

export type UploadFailure = {
  reason: string;
  file: { name: string };
  message: string;
};

export function uploadErrorMessage(
  failure: UploadFailure,
  maxSizeBytes: number,
): string {
  const name = `« ${failure.file.name} »`;
  switch (failure.reason) {
    case "invalid-type":
      return `Le fichier ${name} n’est pas un PDF : seuls les PDF sont acceptés.`;
    case "file-too-large": {
      const mb = Math.round(maxSizeBytes / (1024 * 1024));
      return `Le fichier ${name} dépasse la taille maximale de ${mb} Mo.`;
    }
    default:
      return `Impossible de lire ${name}.`;
  }
}
