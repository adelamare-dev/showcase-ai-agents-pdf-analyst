import { test } from "node:test";
import assert from "node:assert/strict";
import {
  autoDelta,
  formatCompact,
  formatNumber,
  formatPercent,
  parseAmount,
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

test("formatCompact abbreviates with a French suffix", () => {
  assert.match(formatCompact(1_500_000), re("^1,5_M$"));
  assert.equal(formatCompact(950), "950");
  assert.equal(formatCompact(-0.25), "-0,3");
});

test("formatPercent takes a ratio", () => {
  assert.match(formatPercent(0.061), re("^6,1_%$"));
  assert.match(formatPercent(-0.03), re("^-3_%$"));
});

test("parseAmount reads French and English amounts", () => {
  assert.equal(parseAmount("94 930,5 M€"), 94_930_500_000);
  assert.equal(parseAmount("94\u202f930,5\u00a0M€"), 94_930_500_000);
  assert.equal(parseAmount("$1,234.5"), 1234.5);
  assert.equal(parseAmount("1,2 Md€"), 1_200_000_000);
  assert.equal(parseAmount("1,234,567"), 1_234_567);
  assert.equal(parseAmount("-12,5 k€"), -12_500);
  assert.equal(parseAmount("n/a"), null);
});

test("parseAmount does not take a word's first letter for a suffix", () => {
  assert.equal(parseAmount("5 mois"), 5);
});

test("autoDelta computes a signed percentage from a comparison caption", () => {
  assert.match(
    autoDelta("94 930 M€", "vs 89 498 M€ au T4 2023") ?? "",
    re("^[+]6,1_%$"),
  );
  assert.match(
    autoDelta("$94,930M", "vs. $89,498M in Q4 FY23") ?? "",
    re("^[+]6,1_%$"),
  );
  assert.match(
    autoDelta("12 M€", "contre 10 M€ l'an dernier") ?? "",
    re("^[+]20_%$"),
  );
  assert.match(
    autoDelta("90 k€", "par rapport à 100 k€ précédemment") ?? "",
    re("^-10_%$"),
  );
});

test("autoDelta ignores captions that are not comparisons", () => {
  assert.equal(autoDelta("10", "Record historique"), null);
  assert.equal(autoDelta(undefined, "vs 10"), null);
  assert.equal(autoDelta("10", "vs 0"), null);
});
