// Browser port of the Epitran + PanPhon Japanese phonetic distance.
//
// Cards are scored against a typed kana query at query time. We can't run
// Epitran/PanPhon in the browser, so kana -> feature vectors comes from a
// precomputed lookup table (assets/anki/kana_phon.json, built by
// scripts/build_kana_phon_table.py). The distance itself is a weighted feature
// edit distance, matching PanPhon's weighted_feature_edit_distance.
//
// LIMITATION: tokenization is per-mora longest-match concatenation, so it does
// not reproduce Epitran's whole-word context (ん assimilation, っ gemination,
// ー / trailing-う vowel lengthening). Single-mora and identical-string
// distances are exact; whole-word distances are close and keep relative order.

// syl is feature index 0; a vector with syl==1 is a vowel (syllabic).
const SYL = 0;

function isVowel(vec) {
  return vec[SYL] === 1;
}

// Greedy longest-match: try 2-char units (yoon combos) before 1-char units.
export function kanaToFeatures(kana, table) {
  const units = table.table;
  const out = [];
  let i = 0;
  while (i < kana.length) {
    const ch = kana[i];

    // Vowel lengthening: Epitran turns a ー, or a う that follows a vowel, into
    // the length marker ː (zero feature vectors). Mirror that here so e.g.
    // しゅうみ matches しゅみ closely. A う that *starts* a mora stays a vowel.
    if (ch === "ー" || ch === "う") {
      const prev = out.length ? out[out.length - 1] : null;
      if (prev && isVowel(prev)) {
        i += 1;
        continue;
      }
    }

    let matched = false;
    for (let len = 2; len >= 1; len--) {
      if (i + len > kana.length) continue;
      const slice = kana.slice(i, i + len);
      const vecs = units[slice];
      if (vecs) {
        for (const v of vecs) out.push(v);
        i += len;
        matched = true;
        break;
      }
    }
    if (!matched) {
      // Unknown char (e.g. ー with no vectors, punctuation): skip it.
      i += 1;
    }
  }
  return out;
}

// Sum over the weighted per-feature absolute differences. weights has length 22,
// so only the first 22 feature indices contribute (tone features are ignored).
function substitutionCost(v1, v2, weights) {
  let cost = 0;
  for (let i = 0; i < weights.length; i++) {
    cost += Math.abs(v1[i] - v2[i]) * weights[i];
  }
  return cost;
}

// Standard Levenshtein DP over phoneme vectors with the PanPhon costs.
export function weightedFeatureEditDistance(seqA, seqB, weights, indelCost) {
  const n = seqA.length;
  const m = seqB.length;
  const prev = new Array(m + 1);
  const cur = new Array(m + 1);

  for (let j = 0; j <= m; j++) prev[j] = j * indelCost;

  for (let i = 1; i <= n; i++) {
    cur[0] = i * indelCost;
    for (let j = 1; j <= m; j++) {
      const sub = prev[j - 1] + substitutionCost(seqA[i - 1], seqB[j - 1], weights);
      const del = prev[j] + indelCost;
      const ins = cur[j - 1] + indelCost;
      cur[j] = Math.min(sub, del, ins);
    }
    for (let j = 0; j <= m; j++) prev[j] = cur[j];
  }
  return prev[m];
}

export function phoneticDistance(kanaA, kanaB, table) {
  const a = kanaToFeatures(kanaA, table);
  const b = kanaToFeatures(kanaB, table);
  return weightedFeatureEditDistance(a, b, table.weights, table.indelCost);
}
