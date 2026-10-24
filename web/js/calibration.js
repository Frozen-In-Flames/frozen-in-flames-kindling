// Word calibration (V27). The owner's design: "upload a sample of my
// voice from each of the words it struggles with to give you data to
// mathematically inverse render a solution for the failed words."
//
// This is a calibration layer, not a trained model. A one-take sample of
// a word is measured (analysis.analyzeWordSample), and two things are
// solved from the measurement, in the open, as data stored inside the
// voice profile:
//   1. A verified exception: if the vowel the singer actually produced
//      differs from the reading the rules gave the word, the measured
//      phonemes become this voice's reading of that word.
//   2. An inverse fit: per-phoneme correction offsets (log-space deltas
//      on F1/F2/F3, plus duration scalars) that move the renderer's
//      targets (canonical + bounded profile warp + corrections) onto
//      the measured track. Corrections aggregate per phoneme across
//      words, so what "frozen" teaches about OW also helps "stone".
//
// The renderer applies the ladder: a calibrated word's measured track
// shapes that word directly; beneath it, phoneme corrections; beneath
// those, the V26 bounded profile warp; the floor is canonical. The
// phoneme score from the lyrics is never rewritten here: exceptions are
// keyed by word and applied only when a note is rendered for THIS voice.
//
// Schema (JSON, stored at voice.payload.calibration; a future Python
// port consumes the identical data):
// {
//   kind: "kindling/voice-calibration", version: 1,
//   words: { "<wordKey>": {
//     status: "calibrated" | "rejected", reason: null | string,
//     date: ISO, source: "recorded" | "uploaded", audioSha: sha | null,
//     readingBefore: [phonemes], producedVowel: "OW",
//     measured: { median, early, late, glide, onsetDur, codaDur,
//                 codaPresent, codaRatio, voicedSeconds },
//     fit: { phoneme, d?: [dF1,dF2,dF3], dFrom?: [...], dTo?: [...],
//            durScales: { PH: scalar } },
//     track: { chunkIndex, nucleusPh, keys: [{ u, f: [F1,F2,F3] }] }
//            (key values in renderer TARGET space: warped canonical +
//            solved delta; key times u from the sample's own timing)
//   } },
//   exceptions: { "<wordKey>": { phonemesByChunk: [[...], ...],
//                 measuredVowel, from: "calibration", date } },
//   phonemeOffsets: { PH: { d?, dFrom?, dTo?, dur?, samples } }
// }

import {
  EXCEPTIONS, VOWEL_FORMANTS, DIPHTHONG_FORMANTS, CONSONANTS, isVowel,
  phonemesForWord, warpVowelTarget, wordKey,
} from "./phonemes.js?v=8";

export { wordKey };

const LOG_W = [1, 1, 0.5]; // F3 is estimated noisily; it advises, not rules
function logDist(a, b) {
  let s = 0;
  for (let i = 0; i < 3; i++) s += LOG_W[i] * Math.pow(Math.log(a[i] / b[i]), 2);
  return Math.sqrt(s);
}
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const medianNum = (arr) => {
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

// Canonical articulation durations. This mirrors render.js fixedDur();
// the two must agree, and the renderer remains the authority at render
// time (these are only used to turn measured segment times into ratios).
export function canonicalDur(ph) {
  const c = CONSONANTS[ph];
  if (!c) return 0;
  if (c.cls === "stop") return c.closure + 0.012 + c.vot;
  if (c.cls === "affricate") return c.closure + 0.008 + (CONSONANTS[c.fric].dur || 0.1);
  return c.dur || 0.06;
}

// ---- Readings and the target list ---------------------------------------

export function readingForWord(raw) {
  const key = wordKey(raw);
  const groups = phonemesForWord(key);
  return {
    key, groups,
    flat: groups.flatMap(g => g.phonemes),
    source: EXCEPTIONS[key] ? "exception" : "rule",
  };
}

// Patterns the rule-based reading is known to get wrong (the misses are
// named in RELEASE-NOTES-V26.md). A flag is a reason to calibrate, never
// a claim the reading is wrong for this particular word.
export function knownMissFlags(word, flat) {
  const flags = [];
  for (let i = 0; i + 1 < flat.length; i++) {
    if (flat[i] === "ER" && flat[i + 1] === "R") {
      flags.push({ pattern: "er-r", reason: "doubled r after the r-colored vowel (the known 'river' miss)" });
    }
    if ((flat[i] === "S" && flat[i + 1] === "Z") || (flat[i] === "Z" && flat[i + 1] === "S")) {
      flags.push({ pattern: "s-z", reason: "s/z cluster the rules voice inconsistently (the known 'houses' miss)" });
    }
  }
  if (/[aeiou][^aeiou]en$/.test(word)) {
    flags.push({ pattern: "open-en", reason: "vowel before a final -en: the rules shorten it, but it is often long (the known 'frozen' miss)" });
  }
  return flags;
}

// Common lyric words probed even before any lyrics exist, so the words
// the rules are most likely to misread surface on the list on day one.
export const PROBE_WORDS = [
  "frozen", "river", "houses", "falling", "burning", "heaven", "forever",
  "silence", "hollow", "sorrow", "tomorrow", "thunder", "whisper",
  "scream", "bleeding", "holding", "waiting", "dancing", "running",
  "coming", "leaving", "believe", "electric", "shadow", "window",
  "yellow", "follow", "measure", "pleasure", "treasure", "island",
  "answer", "listen", "often", "sugar", "lightning", "open", "broken",
  "spoken", "golden",
];

// The target list for one voice: every word in the current lyrics, plus
// probe words the rules read unaided or that match a known-miss pattern.
// Each entry carries the current reading and why it is listed.
export function buildTargetList({ calibration, texts = [] } = {}) {
  const seen = new Map();
  const add = (raw, inLyrics) => {
    const key = wordKey(raw);
    if (!key) return;
    if (!seen.has(key)) seen.set(key, { key, inLyrics: false });
    if (inLyrics) seen.get(key).inLyrics = true;
  };
  for (const t of texts) {
    for (const w of String(t || "").split(/[^a-zA-Z]+/)) if (w) add(w, true);
  }
  for (const w of PROBE_WORDS) add(w, false);
  const entries = [];
  for (const { key, inLyrics } of seen.values()) {
    const r = readingForWord(key);
    const flags = knownMissFlags(key, r.flat);
    if (!inLyrics && r.source !== "rule" && !flags.length) continue;
    const stored = calibration && calibration.words ? calibration.words[key] : null;
    const reasons = [];
    if (inLyrics) reasons.push("in your current lyrics");
    if (flags.length) reasons.push(...flags.map(f => f.reason));
    else if (r.source === "rule") reasons.push("read by rules alone; no verified reading on file");
    entries.push({
      word: key,
      reading: r.flat,
      source: r.source,
      flags,
      inLyrics,
      reasons,
      status: stored ? stored.status : "uncalibrated",
      statusReason: stored ? (stored.reason || null) : null,
      producedVowel: stored ? (stored.producedVowel || null) : null,
    });
  }
  const rank = (e) => (e.inLyrics ? 0 : 2) + (e.flags.length ? 0 : 1);
  return entries.sort((a, b) => rank(a) - rank(b));
}

// ---- Vowel identification ------------------------------------------------
// What vowel did the singer actually produce? Two ways to judge, in
// order of trust:
//  1. Against reference renders (the differential method): each
//     candidate vowel is rendered in the word's own chunk context, at
//     the sample's pitch, through the same measurement. The candidate
//     whose MEASURED track sits closest to the sample's measured track
//     wins. Estimator bias is shared by both sides and cancels.
//  2. Against canonical centroids in the voice's warped space (no
//     renderer available).
// Every candidate is scored on BOTH track endpoints: a steady vowel
// predicts early ~= late ~= its center, so a gliding sample prices its
// own glide into a steady candidate's score without a special penalty
// term; a diphthong predicts its two distinct endpoints.
export function scoreCandidates(measurement, observedTargets, references = null) {
  const { early, late } = measurement.nucleus;
  const scores = {};
  for (const ph of Object.keys(VOWEL_FORMANTS)) {
    const ref = references ? references[ph] : null;
    const c = ref ? ref.median : warpVowelTarget(VOWEL_FORMANTS[ph], observedTargets);
    scores[ph] = 0.5 * (logDist(early, c) + logDist(late, c));
  }
  for (const ph of Object.keys(DIPHTHONG_FORMANTS)) {
    const ref = references ? references[ph] : null;
    const [a, b] = DIPHTHONG_FORMANTS[ph];
    const ca = ref ? ref.early : warpVowelTarget(a, observedTargets);
    const cb = ref ? ref.late : warpVowelTarget(b, observedTargets);
    scores[ph] = 0.5 * (logDist(early, ca) + logDist(late, cb));
  }
  return scores;
}

export function identifyProducedVowel(measurement, observedTargets, references = null) {
  const scores = scoreCandidates(measurement, observedTargets, references);
  let best = null;
  for (const [ph, score] of Object.entries(scores)) {
    if (!best || score < best.score) best = { ph, score };
  }
  return { ...best, scores };
}

// The read vowel is the null hypothesis. Measured-space neighbors sit
// close together (the estimator compresses), so a challenger must beat
// the read vowel CLEARLY (score at most 85% of the incumbent's, and at
// least 0.03 better in weighted log space) before the calibration mints
// an exception or re-anchors the fit on it. On a near tie the take is
// treated as the read vowel sung with this voice's offsets, which is
// what a single ambiguous take can honestly support.
export function decideProduced({ measurement, observedTargets, references = null, currentVowel }) {
  const { ph, score, scores } = identifyProducedVowel(measurement, observedTargets, references);
  if (ph === currentVowel) return { ph, score, scores, heldByMargin: false };
  const cur = scores[currentVowel];
  if (cur != null && !(score < cur * 0.85 && cur - score > 0.03)) {
    return { ph: currentVowel, score: cur, scores, heldByMargin: true };
  }
  return { ph, score, scores, heldByMargin: false };
}

// ---- The inverse fit ------------------------------------------------------
// Solve one word from its measurement. Returns { entry, exception } or
// { error } when the word has no vowel nucleus to anchor on. The anchor
// is the word's first vowel nucleus (its primary syllable for the words
// this list surfaces); the measured nucleus is taken to be that vowel.
//
// The fit is differential when a reference measurement is supplied
// (calibrate.js builds one per candidate): the renderer will aim at
// warp(canonical) + delta, and the reference render of that same target
// measures M_ref through the same estimator as the sample's M, so the
// delta that makes the render measure like the sample is, per formant,
// (log M - log M_ref) / gain, where gain is the estimator's measured
// response to a known probe delta (a diagonal Jacobian step; the soft
// formant bumps of this synth respond at well under 1:1, and pretending
// otherwise would undercorrect by that factor). Without a reference,
// delta falls back to log(measured) - log(warped target), gain 1.
export function fitWordCalibration({ word, measurement, observedTargets, references = null, reference = null, gains = null }) {
  const key = wordKey(word);
  const reading = readingForWord(key);
  const nucChunk = reading.groups.findIndex(g => g.nucleus >= 0);
  if (nucChunk < 0) {
    return { error: "That word has no vowel to anchor a measurement on." };
  }
  const group = reading.groups[nucChunk];
  const currentVowel = group.phonemes[group.nucleus];
  const produced = decideProduced({ measurement, observedTargets, references, currentVowel });
  const nuc = measurement.nucleus;
  const ref = reference || (references ? references[produced.ph] : null);
  const solveDelta = (measured, base, gain) => measured.map((f, i) => {
    const g = gain && gain[i] != null ? Math.max(0.08, Math.min(1.5, gain[i])) : 1;
    return clamp(Math.log(f / base[i]) / g, -0.40, 0.40);
  });

  const fit = { phoneme: produced.ph, durScales: {} };
  if (DIPHTHONG_FORMANTS[produced.ph]) {
    const [a, b] = DIPHTHONG_FORMANTS[produced.ph];
    if (ref) {
      fit.dFrom = solveDelta(nuc.early, ref.early, gains && gains.dFrom);
      fit.dTo = solveDelta(nuc.late, ref.late, gains && gains.dTo);
    } else {
      fit.dFrom = solveDelta(nuc.early, warpVowelTarget(a, observedTargets), null);
      fit.dTo = solveDelta(nuc.late, warpVowelTarget(b, observedTargets), null);
    }
  } else if (ref) {
    fit.d = solveDelta(nuc.median, ref.median, gains && gains.d);
  } else {
    fit.d = solveDelta(nuc.median, warpVowelTarget(VOWEL_FORMANTS[produced.ph], observedTargets), null);
  }

  // Duration scalars: measured onset/coda time against the canonical
  // articulation time of the phonemes around the nucleus, as one scalar
  // per side (clamped: a single take should nudge timing, not rewrite it).
  const flatIdx = reading.groups.slice(0, nucChunk).reduce((n, g) => n + g.phonemes.length, 0)
    + group.nucleus;
  const onsetPhs = reading.flat.slice(0, flatIdx);
  const codaPhs = reading.flat.slice(flatIdx + 1);
  const sideScale = (phs, measuredDur) => {
    const canon = phs.reduce((t, ph) => t + canonicalDur(ph), 0);
    if (canon <= 0.02 || measuredDur <= 0.01) return;
    const s = clamp(measuredDur / canon, 0.5, 2);
    for (const ph of phs) fit.durScales[ph] = s;
  };
  // Onset timing is only the nucleus's own onsets when the nucleus sits
  // in the first chunk; earlier chunks would have vowels of their own in
  // the measured onset span. Coda timing is only fitted when no second
  // vowel follows the nucleus (otherwise the "coda" span contains the
  // next syllable, not the coda).
  if (nucChunk === 0) sideScale(onsetPhs, measurement.onsetDur);
  if (measurement.codaPresent && codaPhs.every(ph => !isVowel(ph))) {
    sideScale(codaPhs, measurement.codaDur);
  }

  // Word track for the nucleus, as keys inside the nucleus segment (u
  // is a fraction of the segment, so song tempo cannot distort it). The
  // key TIMES come from the sample (when in its nucleus the measured
  // early/late windows sat); the key VALUES are target-space: the
  // warped canonical target with the solved delta applied. Storing the
  // raw measured values here would be a category error: the estimator
  // reads a render back compressed toward the middle, so measured
  // values used as targets would undershoot the sample they came from.
  const relNucStart = measurement.nucleus.start - measurement.wordStart;
  const trackTimes = nuc.track.map(w => w.t);
  const thirdN = Math.max(1, Math.floor(trackTimes.length / 3));
  const earlyT = medianNum(trackTimes.slice(0, thirdN));
  const lateT = medianNum(trackTimes.slice(trackTimes.length - thirdN));
  const uEarly = clamp((earlyT - relNucStart) / measurement.nucleus.dur, 0.05, 0.45);
  const uLate = clamp((lateT - relNucStart) / measurement.nucleus.dur, 0.55, 0.95);
  let keys;
  if (DIPHTHONG_FORMANTS[produced.ph]) {
    const [a, b] = DIPHTHONG_FORMANTS[produced.ph];
    const wa = warpVowelTarget(a, observedTargets);
    const wb = warpVowelTarget(b, observedTargets);
    keys = [
      { u: uEarly, f: wa.map((f, i) => Math.exp(Math.log(f) + fit.dFrom[i])) },
      { u: uLate, f: wb.map((f, i) => Math.exp(Math.log(f) + fit.dTo[i])) },
    ];
  } else {
    const w = warpVowelTarget(VOWEL_FORMANTS[produced.ph], observedTargets);
    const target = w.map((f, i) => Math.exp(Math.log(f) + fit.d[i]));
    keys = [{ u: 0.3, f: target }, { u: 0.7, f: target.slice() }];
  }
  const track = { chunkIndex: nucChunk, nucleusPh: produced.ph, keys };

  // Verified exception: the produced vowel is not the read vowel, so
  // this voice's reading of the word becomes the measured one.
  let exception = null;
  if (produced.ph !== currentVowel) {
    const groups = reading.groups.map(g => ({ ...g, phonemes: g.phonemes.slice() }));
    groups[nucChunk].phonemes[group.nucleus] = produced.ph;
    exception = {
      phonemesByChunk: groups.map(g => g.phonemes),
      measuredVowel: produced.ph,
      from: "calibration",
    };
  }

  const entry = {
    status: "calibrated",
    reason: null,
    readingBefore: reading.flat,
    producedVowel: produced.ph,
    producedScore: Math.round(produced.score * 1000) / 1000,
    heldByMargin: !!produced.heldByMargin,
    fitMethod: ref ? "differential" : "centroid",
    measured: {
      median: nuc.median, early: nuc.early, late: nuc.late, glide: nuc.glide,
      onsetDur: measurement.onsetDur, codaDur: measurement.codaDur,
      codaPresent: measurement.codaPresent, codaRatio: measurement.codaRatio,
      voicedSeconds: measurement.voicedSeconds,
    },
    fit,
    track,
  };
  return { entry, exception };
}

// ---- Store operations (pure; the caller persists) -------------------------

export function emptyCalibration() {
  return { kind: "kindling/voice-calibration", version: 1, words: {}, exceptions: {}, phonemeOffsets: {} };
}

function cloneCal(calibration) {
  return JSON.parse(JSON.stringify(calibration || emptyCalibration()));
}

// Aggregate per-phoneme corrections across all calibrated words: the
// median of every sample's deltas for that phoneme, so one word's take
// cannot dominate and a correction transfers to every word sharing the
// phoneme. Recomputed from the word entries whenever they change.
export function aggregateOffsets(words) {
  const acc = new Map();
  const push = (ph, field, vec) => {
    if (!acc.has(ph)) acc.set(ph, { d: [], dFrom: [], dTo: [], dur: [], samples: 0 });
    if (vec) acc.get(ph)[field].push(vec);
  };
  for (const entry of Object.values(words || {})) {
    if (!entry || entry.status !== "calibrated" || !entry.fit) continue;
    const a = acc.get(entry.fit.phoneme) || { d: [], dFrom: [], dTo: [], dur: [], samples: 0 };
    acc.set(entry.fit.phoneme, a);
    a.samples++;
    if (entry.fit.d) a.d.push(entry.fit.d);
    if (entry.fit.dFrom) a.dFrom.push(entry.fit.dFrom);
    if (entry.fit.dTo) a.dTo.push(entry.fit.dTo);
  }
  // Duration scalars aggregate per consonant across words too.
  const durAcc = new Map();
  for (const entry of Object.values(words || {})) {
    if (!entry || entry.status !== "calibrated" || !entry.fit) continue;
    for (const [ph, s] of Object.entries(entry.fit.durScales || {})) {
      if (!durAcc.has(ph)) durAcc.set(ph, []);
      durAcc.get(ph).push(s);
    }
  }
  const out = {};
  for (const [ph, a] of acc) {
    const o = { samples: a.samples };
    const medVec = (list) => list.length
      ? [0, 1, 2].map(j => medianNum(list.map(v => v[j]))) : null;
    if (a.d.length) o.d = medVec(a.d);
    if (a.dFrom.length) o.dFrom = medVec(a.dFrom);
    if (a.dTo.length) o.dTo = medVec(a.dTo);
    out[ph] = o;
  }
  for (const [ph, list] of durAcc) {
    out[ph] = out[ph] || { samples: 0 };
    out[ph].dur = medianNum(list);
  }
  return out;
}

export function applyCalibration(calibration, word, { entry, exception, source, audioSha, now }) {
  const cal = cloneCal(calibration);
  const key = wordKey(word);
  cal.words[key] = {
    ...entry,
    date: now || new Date().toISOString(),
    source: source || "uploaded",
    audioSha: audioSha || null,
  };
  if (exception) {
    cal.exceptions[key] = { ...exception, date: now || new Date().toISOString() };
  }
  cal.phonemeOffsets = aggregateOffsets(cal.words);
  return cal;
}

export function applyRejection(calibration, word, reason, now) {
  const cal = cloneCal(calibration);
  const key = wordKey(word);
  cal.words[key] = {
    status: "rejected",
    reason,
    date: now || new Date().toISOString(),
    source: null, audioSha: null,
    readingBefore: readingForWord(key).flat,
    producedVowel: null, measured: null, fit: null, track: null,
  };
  cal.phonemeOffsets = aggregateOffsets(cal.words);
  return cal;
}

export function clearCalibration(calibration, word) {
  const cal = cloneCal(calibration);
  const key = wordKey(word);
  delete cal.words[key];
  delete cal.exceptions[key];
  cal.phonemeOffsets = aggregateOffsets(cal.words);
  return cal;
}

export function calibrationSummary(calibration) {
  const words = (calibration && calibration.words) || {};
  let calibrated = 0, rejected = 0;
  for (const w of Object.values(words)) {
    if (w.status === "calibrated") calibrated++;
    else if (w.status === "rejected") rejected++;
  }
  return { calibrated, rejected };
}

// ---- Renderer resolution ---------------------------------------------------
// What one note gets from the calibration layer, per the ladder:
//   word track (this word, measured) > phoneme offsets (aggregated)
//   > profile warp (applied inside the renderer, as in V26) > canonical.
// Returns null when the voice has no calibration at all, so uncalibrated
// rendering is byte-identical to V26.
export function resolveNoteCalibration(calibration, note) {
  if (!calibration) return null;
  const out = {};
  const offsets = calibration.phonemeOffsets;
  if (offsets && Object.keys(offsets).length) out.offsets = offsets;
  const key = note.word;
  if (key && note.chunkIndex != null) {
    const ex = calibration.exceptions ? calibration.exceptions[key] : null;
    if (ex && ex.phonemesByChunk && ex.phonemesByChunk[note.chunkIndex]) {
      out.phonemes = ex.phonemesByChunk[note.chunkIndex].slice();
    }
    const w = calibration.words ? calibration.words[key] : null;
    if (w && w.status === "calibrated" && w.track && w.track.chunkIndex === note.chunkIndex) {
      out.track = w.track;
    }
  }
  return (out.offsets || out.phonemes || out.track) ? out : null;
}
