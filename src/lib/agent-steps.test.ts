import { test } from "node:test";
import assert from "node:assert/strict";
import { isToolFailure, TOOL_STEPS } from "./agent-steps.ts";

test("isToolFailure recognises the agent's provider-error prefix", () => {
  assert.equal(isToolFailure("MISTRAL_ERROR: quota exceeded"), true);
  assert.equal(isToolFailure("MISTRAL_ERROR: "), true);
});

test("isToolFailure ignores ordinary results", () => {
  assert.equal(isToolFailure('{"title":"ok"}'), false);
  assert.equal(isToolFailure("a MISTRAL_ERROR: mid-string"), false);
  assert.equal(isToolFailure(""), false);
});

test("isToolFailure ignores non-string results", () => {
  assert.equal(isToolFailure(undefined), false);
  assert.equal(isToolFailure(null), false);
  assert.equal(isToolFailure({ a: 1 }), false);
});

test("every tool has a failed label", () => {
  for (const step of Object.values(TOOL_STEPS)) {
    assert.ok(step.failed.length > 0);
  }
});
