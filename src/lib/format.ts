/* French number formatting and amount parsing. Pure functions with no
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

const SUFFIX_MULTIPLIER: Record<string, number> = {
  k: 1e3,
  m: 1e6,
  md: 1e9,
  b: 1e9,
};

/* Whitespace used as a thousands separator ("94 930", with U+00A0 or
 * U+202F) is dropped; a group is exactly three digits, so "T4 2023" keeps
 * its space. */
const THOUSANDS_SPACE = /(\d)[\s\u00a0\u202f](?=\d{3}(?!\d))/g;

/* A suffix only counts when no letter follows it, so "5 mois" is 5, not 5 M. */
const AMOUNT =
  /([-\u2212]?)(\d(?:[\d.,]*\d)?)\s*(?:(Md|[kKmMbB])(?![A-Za-z\u00c0-\u00ff]))?/;

/** Reads the first amount of a free-form string ("94 930,5 M€", "$1,234.5",
 *  "1,2 Md€"). When "." and "," both appear the last one is the decimal
 *  mark; a lone separator is a decimal mark unless it repeats. */
export function parseAmount(s: string): number | null {
  if (typeof s !== "string") return null;
  const m = s.replace(THOUSANDS_SPACE, "$1").match(AMOUNT);
  if (!m) return null;
  const [, sign, digits, rawSuffix] = m;

  const lastDot = digits.lastIndexOf(".");
  const lastComma = digits.lastIndexOf(",");
  let normalized: string;
  if (lastDot >= 0 && lastComma >= 0) {
    const decimal = lastDot > lastComma ? "." : ",";
    const thousands = decimal === "." ? /,/g : /\./g;
    normalized = digits.replace(thousands, "").replace(decimal, ".");
  } else {
    const sep = lastDot >= 0 ? "." : lastComma >= 0 ? "," : "";
    const repeated = sep !== "" && digits.indexOf(sep) !== digits.lastIndexOf(sep);
    normalized = repeated ? digits.split(sep).join("") : digits.replace(",", ".");
  }

  const n = parseFloat(normalized);
  if (!isFinite(n)) return null;
  const mult = rawSuffix ? SUFFIX_MULTIPLIER[rawSuffix.toLowerCase()] : 1;
  // Rounding strips the binary noise of e.g. 1.2 * 1e9.
  const value = Math.round(n * mult * 1e6) / 1e6;
  return sign ? -value : value;
}

const COMPARISON =
  /\bvs\b|\bversus\b|\bcontre\b|par rapport|pr[eé]c[eé]dent|ant[eé]rieur|\bfrom\b|compared|\bprior\b|previous|\blast\b|relative to/i;

/** Fallback for a missing `delta`: when the caption holds a prior-period
 *  value ("vs 89 498 M€ au T4 2023"), computes the movement of `value`
 *  against it, as "+6,1 %". Returns null when no comparison can be read. */
export function autoDelta(value?: string, caption?: string): string | null {
  if (!value || !caption || !COMPARISON.test(caption)) return null;
  const current = parseAmount(value);
  const prior = parseAmount(caption);
  if (current == null || prior == null || prior === 0) return null;
  const pct = ((current - prior) / Math.abs(prior)) * 100;
  if (!isFinite(pct)) return null;
  // One decimal under 10 %, whole percents beyond: easier to scan.
  const rounded = Math.abs(pct) < 10 ? Math.round(pct * 10) / 10 : Math.round(pct);
  // A movement that rounds to zero carries no sign.
  if (rounded === 0) return formatPercent(0);
  return `${rounded > 0 ? "+" : ""}${formatPercent(rounded / 100)}`;
}
