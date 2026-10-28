import { test } from "node:test";
import assert from "node:assert/strict";
import { uploadErrorMessage } from "./upload-errors.ts";

const file = { name: "rapport.docx" };
const MAX = 20 * 1024 * 1024;

test("a wrong file type is reported in French", () => {
  assert.equal(
    uploadErrorMessage({ reason: "invalid-type", file, message: "en" }, MAX),
    "Le fichier « rapport.docx » n’est pas un PDF : seuls les PDF sont acceptés.",
  );
});

test("an oversized file names the limit in Mo", () => {
  assert.equal(
    uploadErrorMessage({ reason: "file-too-large", file, message: "en" }, MAX),
    "Le fichier « rapport.docx » dépasse la taille maximale de 20 Mo.",
  );
});

test("an unknown reason never leaks the English message", () => {
  assert.equal(
    uploadErrorMessage({ reason: "upload-failed", file, message: "boom" }, MAX),
    "Impossible de lire « rapport.docx ».",
  );
});
