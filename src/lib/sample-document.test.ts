import { test } from "node:test";
import assert from "node:assert/strict";
import type { Message } from "@ag-ui/core";
import { documentPart, withSampleDocument } from "./sample-document.ts";

const doc = {
  value: "page one text",
  loaded: { filename: "insee.pdf", pages: 3, keptPages: 3, truncated: false, chars: 13 },
};

function userMessage(id: string, content: string | object[]): Message {
  return { id, role: "user", content } as Message;
}

test("the document part carries the text, its MIME type and the file metadata", () => {
  assert.deepEqual(documentPart(doc), {
    type: "document",
    source: { type: "data", value: "page one text", mimeType: "text/plain" },
    metadata: { filename: "insee.pdf", pages: 3, originalMime: "application/pdf" },
  });
});

test("a string content becomes a text part followed by the document", () => {
  const out = withSampleDocument([userMessage("u1", "Quel PIB ?")], doc);
  assert.deepEqual(out, [
    userMessage("u1", [{ type: "text", text: "Quel PIB ?" }, documentPart(doc)]),
  ]);
});

test("an array content keeps its parts and gets the document appended", () => {
  const parts = [
    { type: "text", text: "a" },
    { type: "text", text: "b" },
  ];
  const out = withSampleDocument([userMessage("u1", parts)], doc);
  assert.deepEqual(out, [userMessage("u1", [...parts, documentPart(doc)])]);
});

test("nothing happens without a user message", () => {
  const messages: Message[] = [
    { id: "a1", role: "assistant", content: "Bonjour" } as Message,
  ];
  assert.equal(withSampleDocument(messages, doc), null);
  assert.equal(withSampleDocument([], doc), null);
});

test("nothing happens when an earlier message already carries a document", () => {
  const messages = [
    userMessage("u1", [{ type: "text", text: "a" }, documentPart(doc)]),
    { id: "a1", role: "assistant", content: "ok" } as Message,
    userMessage("u2", "suite"),
  ];
  assert.equal(withSampleDocument(messages, doc), null);
});

test("nothing happens on a follow-up: the thread holds more than one user message", () => {
  const messages = [
    userMessage("u1", "premier"),
    { id: "a1", role: "assistant", content: "ok" } as Message,
    userMessage("u2", "dernier"),
  ];
  assert.equal(withSampleDocument(messages, doc), null);
});

test("nothing happens when the single user message already carries a document", () => {
  const messages = [
    userMessage("u1", [{ type: "text", text: "a" }, documentPart(doc)]),
  ];
  assert.equal(withSampleDocument(messages, doc), null);
});

test("nothing happens once the first message holds the document as text", () => {
  const messages = [
    userMessage("u1", [{ type: "text", text: "[Document: x.pdf]\npage one text" }]),
    userMessage("u2", "suite"),
  ];
  assert.equal(withSampleDocument(messages, doc), null);
});

test("the assistant messages around a single user message are kept", () => {
  const assistant = { id: "a1", role: "assistant", content: "ok" } as Message;
  const messages = [userMessage("u1", "premier"), assistant];
  const out = withSampleDocument(messages, doc);
  assert.ok(out);
  assert.equal(out.length, 2);
  assert.equal(out[1], assistant);
});

test("the input array and its messages are not mutated", () => {
  const parts = [{ type: "text", text: "a" }];
  const messages = [userMessage("u1", parts)];
  const snapshot = structuredClone(messages);
  withSampleDocument(messages, doc);
  assert.deepEqual(messages, snapshot);
  assert.equal(parts.length, 1);
});
