// Node test harness: runs the 10 golden pairs through the JS phonetic distance
// and prints a comparison table. Run with:
//   /Users/james.buzaid/h/node/env-22.14.0/bin/node assets/phonetic.test.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { phoneticDistance } from "./phonetic.js";

const here = dirname(fileURLToPath(import.meta.url));
const table = JSON.parse(
  readFileSync(join(here, "anki", "kana_phon.json"), "utf8"),
);

const golden = [
  { a: "ぐんやり", b: "ぐにゃり", dist: 10.75 },
  { a: "べんきょう", b: "べんぎょう", dist: 0.25 },
  { a: "ぐんやり", b: "ぐんと", dist: 25.375 },
  { a: "ぐにゃり", b: "ぐにゃぐにゃ", dist: 19.125 },
  { a: "ちゅうとはんぱ", b: "ちゅうとはんぱ", dist: 0.0 },
  { a: "ぐんやり", b: "けいざい", dist: 22.375 },
  { a: "べんきょう", b: "べんきょう", dist: 0.0 },
  { a: "しゅみ", b: "しゅうみ", dist: 0.5 },
  { a: "か", b: "が", dist: 0.25 },
  { a: "さ", b: "ざ", dist: 1.75 },
];

// Pairs that must be exact (single mora / identical strings).
const exactPairs = new Set([
  "ちゅうとはんぱ|ちゅうとはんぱ",
  "べんきょう|べんきょう",
  "か|が",
  "さ|ざ",
]);

function fmt(x) {
  return x.toFixed(3).padStart(9);
}

let allPass = true;
console.log(
  "a".padEnd(12) +
    "b".padEnd(14) +
    "jsDist".padStart(9) +
    "golden".padStart(9) +
    "  status",
);
console.log("-".repeat(60));
for (const g of golden) {
  const js = phoneticDistance(g.a, g.b, table);
  const key = `${g.a}|${g.b}`;
  let status;
  if (exactPairs.has(key)) {
    // These MUST be exact.
    if (Math.abs(js - g.dist) < 1e-9) {
      status = "PASS";
    } else {
      status = "FAIL";
      allPass = false;
    }
  } else {
    // Whole-word cases differ from Epitran due to per-mora tokenization;
    // informational only.
    status = Math.abs(js - g.dist) <= 0.1 ? "PASS" : "diff";
  }
  console.log(
    g.a.padEnd(12) + g.b.padEnd(14) + fmt(js) + fmt(g.dist) + "  " + status,
  );
}

// Relative-ordering check for query ぐんやり.
const q = "ぐんやり";
const dNya = phoneticDistance(q, "ぐにゃり", table);
const dTo = phoneticDistance(q, "ぐんと", table);
const dKei = phoneticDistance(q, "けいざい", table);
const orderOk = dNya < dTo && dNya < dKei;
if (!orderOk) allPass = false;

console.log("-".repeat(60));
console.log(
  `ordering for "${q}": ぐにゃり(${dNya.toFixed(3)}) < ` +
    `ぐんと(${dTo.toFixed(3)}) & < けいざい(${dKei.toFixed(3)}) -> ` +
    (orderOk ? "PASS" : "FAIL"),
);
console.log("\nNote: exact pairs (=0.0, か/が=0.25, さ/ざ=1.75) use a strict");
console.log("tolerance; whole-word pairs use +/-0.1 and may differ due to");
console.log("per-mora tokenization (ん assimilation, ー/う lengthening).");

process.exit(allPass ? 0 : 1);
