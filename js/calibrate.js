// Calibration orchestration (V27): the parts of word calibration that
// need the renderer and the analyzer together. Kept out of
// calibration.js (pure data and math) and out of render.js (which the
// calibration layer must not depend on cyclically).
//
// The method, end to end, for one word and one take:
//   1. Measure the sample (analysis.analyzeWordSample). The quality
//      gate lives there; a refusal here writes a rejected status with
//      the reason and nothing else. Never fit garbage silently.
//   2. Build references: every candidate vowel rendered in the word's
//      own nucleus chunk, at the sample's measured pitch, uncalibrated,
//      and measured with the same estimator. Identification is then a
//      comparison in measured space, where estimator bias is shared.
//   3. Probe the response gain: re-render the winning candidate with a
//      known +0.12 log probe delta per formant and measure how far the
//      measurement actually moves. The synth's formant bumps are soft,
//      so the response is well under 1:1; the solver divides by the
//      measured gain (a diagonal Jacobian step) instead of pretending.
//   4. Fit (calibration.fitWordCalibration) and store
//      (calibration.applyCalibration): verified exception if the
//      produced vowel is not the read vowel, per-phoneme corrections
//      aggregated across words, and the measured nucleus track.

import {
  VOWEL_FORMANTS, DIPHTHONG_FORMANTS,
} from "./phonemes.js?v=8";
import { mulberry32, freqToMidi } from "./audio.js?v=8";
import { synthVocalNote } from "./render.js?v=8";
import { analyzeWordSample } from "./analysis.js?v=8";
import {
  readingForWord, decideProduced, fitWordCalibration,
  applyCalibration, applyRejection,
} from "./calibration.js?v=8";

const RENDER_SR = 44100; // render.js synthesizes at this rate
const PROBE = 0.12;
export const CANDIDATE_VOWELS = [
  ...Object.keys(VOWEL_FORMANTS), ...Object.keys(DIPHTHONG_FORMANTS),
];

export function referenceContext({ word, sampleMeasurement, observedTargets }) {
  const reading = readingForWord(word);
  const nucChunk = reading.groups.findIndex(g => g.nucleus >= 0);
  if (nucChunk < 0) return null;
  const f0 = sampleMeasurement.nucleus ? sampleMeasurement.nucleus.f0 : null;
  return {
    reading,
    nucChunk,
    group: reading.groups[nucChunk],
    midi: f0 ? Math.round(freqToMidi(f0)) : 55,
    dur: Math.max(0.5, Math.min(1.1, sampleMeasurement.wordDur || 0.65)),
    observedTargets,
  };
}

// Render one candidate vowel in the word's nucleus chunk and measure
// it. extraOffsets applies a probe (or test) correction to the
// candidate so the solver can watch the measurement respond.
export function renderCandidate(ctx, ph, extraOffsets = null, seed = 1234) {
  const phonemes = ctx.group.phonemes.slice();
  phonemes[ctx.group.nucleus] = ph;
  const note = { syllable: "", phonemes, midi: ctx.midi, dur: ctx.dur };
  if (extraOffsets) note.cal = { offsets: extraOffsets };
  const buf = synthVocalNote(note, mulberry32(seed), { observedTargets: ctx.observedTargets });
  const m = analyzeWordSample(buf, RENDER_SR);
  if (!m.ok) return null;
  return {
    median: m.nucleus.median, early: m.nucleus.early,
    late: m.nucleus.late, glide: m.nucleus.glide,
  };
}

export function buildReferences(ctx) {
  const refs = {};
  for (const ph of CANDIDATE_VOWELS) {
    const r = renderCandidate(ctx, ph);
    if (r) refs[ph] = r;
  }
  return refs;
}

// Measure how far the estimator's reading moves per unit of applied
// log delta, per formant, at this operating point. Same seed as the
// base reference so excitation noise cancels between the two renders.
export function probeGains(ctx, winner, baseRef) {
  const gainsFor = (field, which) => {
    const gains = [];
    for (let j = 0; j < 3; j++) {
      const d = [0, 0, 0];
      d[j] = PROBE;
      const offsets = {
        [winner]: which === "from" ? { dFrom: d }
          : which === "to" ? { dTo: d } : { d },
      };
      const probe = renderCandidate(ctx, winner, offsets);
      if (!probe || !baseRef || !baseRef[field][j]) { gains.push(1); continue; }
      gains.push(Math.log(probe[field][j] / baseRef[field][j]) / PROBE);
    }
    return gains;
  };
  if (DIPHTHONG_FORMANTS[winner]) {
    return { dFrom: gainsFor("early", "from"), dTo: gainsFor("late", "to") };
  }
  return { d: gainsFor("median", null) };
}

// The full solve for one word and one take. Returns either
// { refused, calibration } (the gate or the fit said no; the rejection
// is stored with its reason, and no exception, offset, or track is
// written) or { calibration, entry, exception, produced, measurement }.
export function solveWordCalibration({
  calibration, word, mono, sampleRate, observedTargets, source, audioSha, now,
}) {
  const measurement = analyzeWordSample(mono, sampleRate);
  if (!measurement.ok) {
    return {
      refused: measurement.reason,
      calibration: applyRejection(calibration, word, measurement.reason, now),
    };
  }
  const ctx = referenceContext({ word, sampleMeasurement: measurement, observedTargets });
  if (!ctx) {
    const reason = "That word has no vowel to anchor a measurement on.";
    return { refused: reason, calibration: applyRejection(calibration, word, reason, now) };
  }
  const references = buildReferences(ctx);
  const currentVowel = ctx.group.phonemes[ctx.group.nucleus];
  const produced = decideProduced({ measurement, observedTargets, references, currentVowel });
  const gains = probeGains(ctx, produced.ph, references[produced.ph]);
  const { entry, exception, error } = fitWordCalibration({
    word, measurement, observedTargets, references, gains,
  });
  if (error) {
    return { refused: error, calibration: applyRejection(calibration, word, error, now) };
  }
  return {
    calibration: applyCalibration(calibration, word, { entry, exception, source, audioSha, now }),
    entry, exception, produced, measurement,
  };
}
