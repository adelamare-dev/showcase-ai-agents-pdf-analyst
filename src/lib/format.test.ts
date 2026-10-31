import { test } from "node:test";
import assert from "node:assert/strict";
import {
  formatCompact,
  formatNumber,
  formatPercent,
  formatTableNumber,
  toneOfDelta,
} from "./format.ts";

// ICU uses U+202F for thousands and U+00A0 before % and compact suffixes;
// older data accepts either, so the tests do too.
const SP = "[\u00a0\u202f]";
const re = (src: string) => new RegExp(src.replaceAll("_", SP));

test("formatNumber groups thousands and uses a decimal comma", () => {
  assert.match(formatNumber(1234.5), re("^1_234,5$"));
  assert.equal(formatNumber(-0.8), "-0,8");
  assert.equal(formatNumber(950), "950");
});

test("formatTableNumber leaves 4-digit values ungrouped", () => {
  assert.equal(formatTableNumber(2023), "2023");
  assert.match(formatTableNumber(12345), re("^12_345$"));
  assert.match(formatTableNumber(1234.5), re("^1234,5$"));
});

test("formatCompact abbreviates with a French suffix", () => {
  assert.match(formatCompact(1_500_000), re("^1,5_M$"));
  assert.equal(formatCompact(950), "950");
  assert.equal(formatCompact(-0.25), "-0,3");
});

test("formatPercent takes a ratio", () => {
  assert.match(formatPercent(0.061), re("^6,1_%$"));
  assert.match(formatPercent(-0.03), re("^-3_%$"));
});

test("toneOfDelta reads the tone from the leading sign", () => {
  assert.equal(toneOfDelta("-0,2 %"), "negative");
  assert.equal(toneOfDelta("\u22120,2 %"), "negative");
  assert.equal(toneOfDelta("  -3 %"), "negative");
  assert.equal(toneOfDelta("+6,1 %"), "positive");
  assert.equal(toneOfDelta("0,0 %"), "neutral");
  assert.equal(toneOfDelta("+0,0 %"), "neutral");
  assert.equal(toneOfDelta("-0,0 pt"), "neutral");
  assert.equal(toneOfDelta("−0 %"), "neutral");
  assert.equal(toneOfDelta("0 %"), "neutral");
  assert.equal(toneOfDelta("+0,4 %"), "positive");
  assert.equal(toneOfDelta("-10 %"), "negative");
  assert.equal(toneOfDelta("+0,0 % vs T2"), "neutral");
  assert.equal(toneOfDelta("+0,0 pt (2025)"), "neutral");
  assert.equal(toneOfDelta("-0,2 % vs T1"), "negative");
  assert.equal(toneOfDelta("+1,5 %"), "positive");
  assert.equal(toneOfDelta("+10 %"), "positive");
  assert.equal(toneOfDelta("0,5 %"), "neutral");
  assert.equal(toneOfDelta("5 pts"), "neutral");
  assert.equal(toneOfDelta("T2 2026"), "neutral");
  assert.equal(toneOfDelta("vs -3"), "neutral");
  assert.equal(toneOfDelta(""), "neutral");
});
