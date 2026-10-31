/* French number formatting and delta tone. Pure functions with no
 * imports: Node runs this file directly in the unit tests. */

const NUMBER = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
const COMPACT = new Intl.NumberFormat("fr-FR", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const PERCENT = new Intl.NumberFormat("fr-FR", {
  style: "percent",
  maximumFractionDigits: 1,
});

// "min2" groups only from five digits, so a year stays "2023" in a table
// while 12345 becomes "12 345".
const TABLE_NUMBER = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 2,
  useGrouping: "min2",
});

export const formatNumber = (n: number): string => NUMBER.format(n);

/** Table cells: like `formatNumber`, but 4-digit values (years) are not grouped. */
export const formatTableNumber = (n: number): string => TABLE_NUMBER.format(n);

/** Axis ticks and tooltips: 1 500 000 becomes "1,5 M". */
export const formatCompact = (n: number): string => COMPACT.format(n);

/** Takes a ratio: 0.061 becomes "6,1 %". */
export const formatPercent = (ratio: number): string => PERCENT.format(ratio);

/** Tone of an explicit delta from its sign: a leading "-" or "−" (U+2212) is
 *  negative, "+" is positive, anything else is neutral. A signed number whose
 *  digits are all zero ("+0,0 %", "-0,0 pt") is neutral whatever its sign. */
export function toneOfDelta(delta: string): "positive" | "negative" | "neutral" {
  const m = delta.trim().match(/^([-+\u2212])\s*([\d.,]*)/);
  if (!m || !/[1-9]/.test(m[2])) return "neutral";
  return m[1] === "+" ? "positive" : "negative";
}
