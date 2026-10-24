// Phoneme layer (V26). The owner's design: the words exist first, as real
// English, independent of any voice. A lyric line becomes a phoneme score:
// every syllable chunk compose.js produces gains an ordered phoneme list
// (onset consonants, vowel nucleus, coda consonants). The renderer pushes
// excitation (shaped noise for the whisper substrate, a harmonic source for
// the voiced retune) through formant targets that MOVE along this score.
//
// The voice profile never reaches this layer. It enters later, in the
// renderer, as warpVowelTarget(): a bounded pull of formant targets toward
// the profile's observed vowel space. A phoneme chosen from the lyrics is
// invariant under any profile; the profile can shape, never substitute.
//
// No dependencies. Deterministic. ARPAbet-style names.

// ---- Inventory: 39 phonemes -------------------------------------------
// Vowels: [F1, F2, F3] in Hz (standard published targets, adult reference).
export const VOWEL_FORMANTS = {
  IY: [270, 2290, 3010], IH: [390, 1990, 2550], EH: [530, 1840, 2480],
  AE: [660, 1720, 2410], AA: [730, 1090, 2440], AO: [570, 840, 2410],
  UH: [440, 1020, 2240], UW: [300, 870, 2240], AH: [520, 1190, 2390],
  ER: [490, 1350, 1690], // low F3 is what makes ER sound r-colored
};
// Diphthongs: two-target trajectories [from, to].
export const DIPHTHONG_FORMANTS = {
  AY: [[730, 1090, 2440], [390, 1990, 2550]],
  AW: [[730, 1090, 2440], [440, 1020, 2240]],
  OY: [[570, 840, 2410], [390, 1990, 2550]],
  EY: [[530, 1840, 2480], [390, 1990, 2550]],
  OW: [[570, 840, 2410], [440, 1020, 2240]],
};
// Consonants. cls drives articulation in the renderer:
//  stop: closure (silent, or low murmur when voiced) + burst + VOT gap.
//  fricative: band-shaped noise; voiced ones mix in the harmonic source.
//  affricate: stop closure+burst flowing into its fricative.
//  nasal: low-formant murmur, reduced amplitude.
//  liquid/glide: voiced moving-formant segments.
export const CONSONANTS = {
  P:  { cls: "stop", voiced: false, closure: 0.070, vot: 0.055, burstBand: [700, 3500], burstGain: 0.50 },
  B:  { cls: "stop", voiced: true,  closure: 0.050, vot: 0.012, burstBand: [500, 3000], burstGain: 0.35 },
  T:  { cls: "stop", voiced: false, closure: 0.065, vot: 0.060, burstBand: [3500, 8000], burstGain: 0.55 },
  D:  { cls: "stop", voiced: true,  closure: 0.045, vot: 0.014, burstBand: [3000, 7000], burstGain: 0.40 },
  K:  { cls: "stop", voiced: false, closure: 0.075, vot: 0.055, burstBand: [1500, 3500], burstGain: 0.55 },
  G:  { cls: "stop", voiced: true,  closure: 0.050, vot: 0.014, burstBand: [1200, 3000], burstGain: 0.40 },
  F:  { cls: "fricative", voiced: false, dur: 0.085, band: [4000, 8500], gain: 0.34 },
  V:  { cls: "fricative", voiced: true,  dur: 0.075, band: [3000, 7000], gain: 0.30 },
  TH: { cls: "fricative", voiced: false, dur: 0.080, band: [5000, 9000], gain: 0.26 },
  DH: { cls: "fricative", voiced: true,  dur: 0.070, band: [4000, 8000], gain: 0.24 },
  S:  { cls: "fricative", voiced: false, dur: 0.095, band: [5500, 9500], gain: 0.55 },
  Z:  { cls: "fricative", voiced: true,  dur: 0.085, band: [4500, 8500], gain: 0.45 },
  SH: { cls: "fricative", voiced: false, dur: 0.110, band: [2400, 6000], gain: 0.50 },
  ZH: { cls: "fricative", voiced: true,  dur: 0.100, band: [2200, 5500], gain: 0.42 },
  HH: { cls: "fricative", voiced: false, dur: 0.060, band: [800, 5000], gain: 0.22, breath: true },
  CH: { cls: "affricate", voiced: false, closure: 0.045, vot: 0.010, fric: "SH" },
  JH: { cls: "affricate", voiced: true,  closure: 0.035, vot: 0.008, fric: "ZH" },
  M:  { cls: "nasal", voiced: true, dur: 0.075, formants: [250, 950, 2100], gain: 0.55 },
  N:  { cls: "nasal", voiced: true, dur: 0.070, formants: [250, 1050, 2300], gain: 0.55 },
  NG: { cls: "nasal", voiced: true, dur: 0.080, formants: [260, 1150, 2500], gain: 0.55 },
  L:  { cls: "liquid", voiced: true, dur: 0.065, formants: [360, 1300, 2600], gain: 0.85 },
  R:  { cls: "liquid", voiced: true, dur: 0.060, formants: [470, 1180, 1620], gain: 0.9 },
  W:  { cls: "glide", voiced: true, dur: 0.070, formants: [300, 870, 2240], gain: 0.9 },
  Y:  { cls: "glide", voiced: true, dur: 0.060, formants: [270, 2290, 3010], gain: 0.9 },
};
export const PHONEME_NAMES = [
  ...Object.keys(VOWEL_FORMANTS), ...Object.keys(DIPHTHONG_FORMANTS),
  ...Object.keys(CONSONANTS),
];
export function isVowel(ph) { return ph in VOWEL_FORMANTS || ph in DIPHTHONG_FORMANTS; }
export function formantTargets(ph) {
  if (ph in VOWEL_FORMANTS) return [VOWEL_FORMANTS[ph]];
  if (ph in DIPHTHONG_FORMANTS) return DIPHTHONG_FORMANTS[ph];
  const c = CONSONANTS[ph];
  if (c && c.formants) return [c.formants];
  return null; // obstruents ride the track between voiced neighbors
}

// ---- Profile warp -------------------------------------------------------
// The retune. Each canonical target is pulled toward the profile's nearest
// observed vowel centroid by at most WARP_MAX of the log-space distance,
// and the resulting formants are clamped to a sane band. The phoneme list
// itself is never touched: this moves Hz values, not identities.
export const WARP_MAX = 0.25;
export const FORMANT_CLAMP = [180, 3800];
export function warpVowelTarget(target, observedTargets) {
  if (!observedTargets || !observedTargets.length) return target.slice();
  let best = null, bestD = Infinity;
  for (const o of observedTargets) {
    let d = 0;
    for (let i = 0; i < 3; i++) d += Math.pow(Math.log(target[i] / o[i]), 2);
    if (d < bestD) { bestD = d; best = o; }
  }
  return target.map((f, i) => {
    const pulled = Math.exp(Math.log(f) + WARP_MAX * (Math.log(best[i]) - Math.log(f)));
    return Math.max(FORMANT_CLAMP[0], Math.min(FORMANT_CLAMP[1], pulled));
  });
}
export function observedTargetsFromLabels(labels) {
  const out = [];
  for (const raw of labels || []) {
    const name = String(raw).replace(/\?$/, "");
    if (VOWEL_FORMANTS[name]) out.push(VOWEL_FORMANTS[name]);
  }
  return out;
}

// ---- Grapheme to phoneme -----------------------------------------------
// Exception dictionary: common irregular words, data-driven so it grows by
// adding lines. Values are space-separated phoneme names.
export const EXCEPTIONS = {
  the: "DH AH", of: "AH V", love: "L AH V", night: "N AY T", heart: "HH AA R T",
  this: "DH IH S", that: "DH AE T", them: "DH EH M", then: "DH EH N",
  than: "DH AE N", those: "DH OW Z", these: "DH IY Z", smooth: "S M UW DH",
  fire: "F AY R", one: "W AH N", two: "T UW", who: "HH UW", to: "T UW",
  do: "D UW", you: "Y UW", said: "S EH D", says: "S EH Z", they: "DH EY",
  there: "DH EH R", their: "DH EH R", were: "W ER", been: "B IH N",
  women: "W IH M AH N", busy: "B IH Z IY", pretty: "P R IH T IY",
  are: "AA R", eye: "AY", light: "L AY T", right: "R AY T", high: "HH AY",
  though: "DH OW", thought: "TH AO T", through: "TH R UW", enough: "IH N AH F",
  laugh: "L AE F", friend: "F R EH N D", again: "AH G EH N", soul: "S OW L",
  could: "K UH D", would: "W UH D", should: "SH UH D", know: "N OW",
  own: "OW N", now: "N AW", how: "HH AW", down: "D AW N", town: "T AW N",
  brown: "B R AW N", my: "M AY", by: "B AY", why: "W AY", fly: "F L AY",
  sky: "S K AY", try: "T R AY", music: "M Y UW Z IH K", water: "W AO T ER",
  mother: "M AH DH ER", father: "F AA DH ER", brother: "B R AH DH ER",
  other: "AH DH ER", come: "K AH M", some: "S AH M", done: "D AH N",
  gone: "G AO N", give: "G IH V", get: "G EH T", girl: "G ER L",
  live: "L IH V", have: "HH AE V", move: "M UW V", go: "G OW", no: "N OW",
  so: "S OW", he: "HH IY", she: "SH IY", we: "W IY", me: "M IY", be: "B IY",
  hi: "HH AY", oh: "OW", earth: "ER TH", learn: "L ER N", work: "W ER K",
  word: "W ER D", first: "F ER S T", her: "HH ER", over: "OW V ER",
  after: "AE F T ER", every: "EH V R IY", people: "P IY P AH L",
  little: "L IH T AH L", only: "OW N L IY", really: "R IH L IY",
  great: "G R EY T", break: "B R EY K", book: "B UH K", good: "G UH D",
  look: "L UH K", blood: "B L AH D", door: "D AO R", floor: "F L AO R",
  once: "W AH N S", answer: "AE N S ER", listen: "L IH S AH N",
  often: "AO F AH N", sugar: "SH UH G ER", sure: "SH UH R",
  climb: "K L AY M", debt: "D EH T", island: "AY L AH N D",
  choir: "K W AY R", echo: "EH K OW", ghost: "G OW S T",
  hour: "AW R", honest: "AA N AH S T", rhythm: "R IH DH AH M",
  yolk: "Y OW K", toward: "T AO R D", shadow: "SH AE D OW",
  yellow: "Y EH L OW", window: "W IH N D OW", follow: "F AA L OW",
  measure: "M EH ZH ER", pleasure: "P L EH ZH ER", treasure: "T R EH ZH ER",
};

// Letter-span G2P. Returns [{ph, start, end}] with spans over the letters
// of the cleaned word, plus a map from letter index to original index.
function cleanWord(raw) {
  const letters = [], map = [];
  const s = String(raw || "").toLowerCase();
  for (let i = 0; i < s.length; i++) {
    if (s[i] >= "a" && s[i] <= "z") { letters.push(s[i]); map.push(i); }
  }
  return { word: letters.join(""), map };
}

const SHORT_VOWEL = { a: "AE", e: "EH", i: "IH", o: "AA", u: "AH" };
const LONG_VOWEL = { a: "EY", e: "IY", i: "AY", o: "OW", u: "UW" };
const CONS_LETTER = {
  b: "B", d: "D", f: "F", g: "G", h: "HH", j: "JH", k: "K", l: "L", m: "M",
  n: "N", p: "P", r: "R", s: "S", t: "T", v: "V", w: "W", z: "Z",
};

export function g2pWord(raw) {
  const { word: w, map } = cleanWord(raw);
  if (!w) return [];
  if (EXCEPTIONS[w]) {
    const phs = EXCEPTIONS[w].split(" ");
    // Spans: spread evenly; only span starts drive chunk assignment.
    return phs.map((ph, i) => ({
      ph, start: map[Math.floor((i * w.length) / phs.length)] ?? 0,
      end: map[Math.floor(((i + 1) * w.length) / phs.length) - 1] ?? 0,
    }));
  }
  const out = [];
  const push = (ph, start, end) => out.push({ ph, start: map[start] ?? start, end: map[end] ?? end });
  const at = (i) => w[i] || "";
  const isV = (c) => "aeiou".includes(c);
  let i = 0;
  while (i < w.length) {
    const c = w[i], two = w.slice(i, i + 2), three = w.slice(i, i + 3);
    // Multi-letter graphemes first.
    if (three === "igh") { push("AY", i, i + 2); i += 3; continue; }
    if (three === "tch") { push("CH", i, i + 2); i += 3; continue; }
    if (w.slice(i, i + 4) === "tion") { push("SH", i, i + 1); push("AH", i + 2, i + 2); push("N", i + 3, i + 3); i += 4; continue; }
    if (two === "ch") { push("CH", i, i + 1); i += 2; continue; }
    if (two === "sh") { push("SH", i, i + 1); i += 2; continue; }
    if (two === "th") { push("TH", i, i + 1); i += 2; continue; }
    if (two === "ph") { push("F", i, i + 1); i += 2; continue; }
    if (two === "ck") { push("K", i, i + 1); i += 2; continue; }
    if (two === "ng") { push("NG", i, i + 1); i += 2; continue; }
    if (two === "qu") { push("K", i, i); push("W", i + 1, i + 1); i += 2; continue; }
    if (two === "wh") { push("W", i, i + 1); i += 2; continue; }
    if (two === "gh") { i += 2; continue; } // silent in most positions
    if (two === "kn" && i === 0) { push("N", i, i + 1); i += 2; continue; }
    if (two === "wr" && i === 0) { push("R", i, i + 1); i += 2; continue; }
    if (two === "mb" && i + 2 === w.length) { push("M", i, i); i += 2; continue; }
    // Vowel teams first when a vowel starts a two-letter team (ay, ow...).
    if (isV(c)) {
      const team = {
        ee: "IY", ea: "IY", ai: "EY", ei: "EY", ie: "IY", oa: "OW",
        oo: "UW", ou: "AW", oi: "OY", oy: "OY", au: "AO", aw: "AO",
        eu: "UW", ew: "UW", ue: "UW", ui: "UW", ow: "AW", ay: "EY",
        ey: "EY",
      }[two];
      if (team) { push(team, i, i + 1); i += 2; continue; }
    }
    // Vowels and vowel teams.
    if (isV(c) || c === "y") {
      // y as a consonant: word-initial before a vowel, or in "y" glide spots.
      if (c === "y") {
        if (i === 0 && isV(at(i + 1))) { push("Y", i, i); i += 1; continue; }
        if (i > 0 && !isV(at(i - 1)) && (i + 1 === w.length)) { push("IY", i, i); i += 1; continue; }
        if (i > 0 && !isV(at(i - 1))) { push("IH", i, i); i += 1; continue; }
        push("Y", i, i); i += 1; continue;
      }
      // R-controlled vowels: vowel + r colors the vowel; R stays a phoneme.
      if (at(i + 1) === "r") {
        if (two === "ar") push("AA", i, i);
        else if (two === "or") push("AO", i, i);
        else if (two === "er" || two === "ir" || two === "ur") push("ER", i, i);
        else push(SHORT_VOWEL[c], i, i);
        push("R", i + 1, i + 1); i += 2; continue;
      }
      // Magic e: vowel + consonant + final e -> long vowel, e silent.
      // A trailing plural s after the e ("flames") keeps the magic.
      if (at(i + 2) === "e" && at(i + 1) && !isV(at(i + 1))
          && (i + 3 === w.length || (i + 4 === w.length && at(i + 3) === "s"))) {
        push(LONG_VOWEL[c], i, i);
        // The consonant between the vowel and the silent e still sounds.
        const mid = CONS_LETTER[at(i + 1)];
        if (mid) push(mid, i + 1, i + 1);
        i += 3; continue;
      }
      // Silent e before a final s ("flames" tail, "houses").
      if (c === "e" && i + 2 === w.length && at(i + 1) === "s" && i > 0 && !isV(at(i - 1))) {
        i += 1; continue;
      }
      // Word-final vowels are open/long (he, go) except a -> schwa-ish AH.
      if (i + 1 === w.length) {
        if (c === "e") { /* final bare e after consonant handled below */ }
        else if (c === "a") push("AH", i, i);
        else push(LONG_VOWEL[c], i, i);
        i += 1; continue;
      }
      // Final silent e (after a consonant, not magic-e pattern above).
      if (c === "e" && i + 1 === w.length && i > 0 && !isV(at(i - 1))) { i += 1; continue; }
      push(SHORT_VOWEL[c], i, i); i += 1; continue;
    }
    // Single consonant letters with softening rules.
    if (c === "c") {
      push(["e", "i", "y"].includes(at(i + 1)) ? "S" : "K", i, i); i += 1; continue;
    }
    if (c === "g") {
      push(["e", "i", "y"].includes(at(i + 1)) ? "JH" : "G", i, i); i += 1; continue;
    }
    if (c === "x") { push("K", i, i); push("S", i, i); i += 1; continue; }
    if (c === "s" && i + 1 === w.length && out.length) {
      // Word-final s voices after any voiced sound (vowels, voiced
      // consonants), including across a silent e ("flames" -> Z).
      const last = out[out.length - 1].ph;
      const voicedLast = isVowel(last)
        || ["B", "D", "G", "V", "Z", "JH", "L", "R", "M", "N", "NG", "W", "Y"].includes(last);
      push(voicedLast ? "Z" : "S", i, i); i += 1; continue;
    }
    if (CONS_LETTER[c]) {
      // Doubled consonant letters are one sound ("happy", "kiss").
      const ph = CONS_LETTER[c];
      if (!(i > 0 && w[i - 1] === c && out.length && out[out.length - 1].ph === ph)) {
        push(ph, i, i);
      }
      i += 1; continue;
    }
    i += 1; // unknown letter: skip
  }
  return out;
}

// ---- Alignment with compose.js syllabify -------------------------------
// compose.syllabify chunks each word on vowel groups and merges fragments
// under 3 letters. This reproduces that chunking per word (a test pins the
// parity), then assigns each spanned phoneme to the chunk holding the
// start of its letter span, so notes and phonemes stay in lockstep.
export function chunksForWord(raw) {
  // Mirrors compose.syllabify's per-word behavior exactly, including the
  // trailing short buffer becoming its own chunk. The parity test in
  // tests-web pins this equality; if they ever diverge, scoreLine callers
  // detect the count mismatch and fall back to per-chunk scoring.
  const w = String(raw || "").toLowerCase();
  const parts = w.match(/[^aeiouy]*[aeiouy]+[^aeiouy]*/g);
  if (!parts || parts.length <= 1) return [w];
  const out = [];
  let buf = "";
  for (const pt of parts) {
    buf += pt;
    if (buf.replace(/[^a-z]/g, "").length >= 3) { out.push(buf); buf = ""; }
  }
  if (buf) out.push(buf);
  return out.length ? out : [w];
}

export function phonemesForWord(raw) {
  const chunks = chunksForWord(raw);
  const spanned = g2pWord(raw);
  // Chunk letter ranges over the raw (lowercased) word.
  const ranges = [];
  let pos = 0;
  for (const ch of chunks) { ranges.push([pos, pos + ch.length - 1]); pos += ch.length; }
  const groups = chunks.map((chunk) => ({ chunk, phonemes: [] }));
  for (const p of spanned) {
    let gi = ranges.findIndex(([a, b]) => p.start >= a && p.start <= b);
    if (gi < 0) gi = p.start < ranges[0][0] ? 0 : ranges.length - 1;
    groups[gi].phonemes.push(p.ph);
  }
  // Silent-letter chunks (the trailing "e" of "fire") can end up with no
  // phonemes at all. They still own a melody note, so they borrow the
  // nearest preceding vowel as a sustain; identity stays with the word.
  let lastVowel = null;
  for (const g of groups) {
    const ni = g.phonemes.findIndex(isVowel);
    if (ni >= 0) { lastVowel = g.phonemes[ni]; g.nucleus = ni; }
    else if (lastVowel) { g.phonemes = [lastVowel]; g.nucleus = 0; g.sustained = true; }
    else g.nucleus = -1;
  }
  return groups;
}

// The canonical key for a word wherever word-level data is keyed (the
// calibration layer in calibration.js uses the same key): lowercase
// letters only, punctuation and case gone.
export function wordKey(raw) {
  return String(raw || "").toLowerCase().replace(/[^a-z]/g, "");
}

// Score a whole lyric line: an array parallel to syllabify(line) chunks,
// each {chunk, phonemes, nucleus, word, chunkIndex}. word/chunkIndex are
// metadata for layers keyed by word (calibration); they change nothing
// about the score itself. If the chunk parity with compose's syllabify
// ever breaks, callers detect a length mismatch and fall back.
export function scoreLine(line) {
  const words = String(line || "").trim().split(/\s+/).filter(Boolean);
  const out = [];
  for (const w of words) {
    const groups = phonemesForWord(w);
    const key = wordKey(w);
    groups.forEach((g, gi) => { g.word = key; g.chunkIndex = gi; });
    out.push(...groups);
  }
  return out;
}

// Renderer fallback: score a bare syllable chunk as if it were a word.
export function scoreFragment(text) {
  const spanned = g2pWord(text);
  const phonemes = spanned.map((p) => p.ph);
  const ni = phonemes.findIndex(isVowel);
  return { chunk: String(text || ""), phonemes, nucleus: ni };
}
