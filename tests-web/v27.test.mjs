// Kindling V27 (web v8) — word calibration.
// Thresholds are stated BEFORE the results they judge, in the header
// of each section. Mock samples are fabricated with the synth itself:
// a "synthetic voice" is the renderer run under known injected
// per-phoneme offsets, so the solver's job is to recover numbers that
// are known exactly. End-to-end distances average the measurements of
// three renders (different noise seeds) per variant, because a single
// render's segmentation jitters at the ~0.02 log level.
import { synthVocalNote } from "../web/js/render.js?v=8";
import { mulberry32 } from "../web/js/audio.js?v=8";
import { analyzeWordSample } from "../web/js/analysis.js?v=8";
import {
  buildTargetList, calibrationSummary, resolveNoteCalibration,
  applyCalibration, applyRejection,
} from "../web/js/calibration.js?v=8";
import { solveWordCalibration } from "../web/js/calibrate.js?v=8";

const SR = 44100;
let pass = 0, fail = 0;
const check = (name, cond, detail = "") => {
  if (cond) { pass++; console.log(`ok   - ${name}`); }
  else { fail++; console.log(`FAIL - ${name} ${detail}`); }
};
const render = (phonemes, midi, dur, cal = null, seed = 42) =>
  synthVocalNote({ syllable: "", phonemes, midi, dur, ...(cal ? { cal } : {}) }, mulberry32(seed), {});
const W3 = [1, 1, 0.5];
const logDist = (a, b) => Math.sqrt(a.reduce((s, v, i) => s + W3[i] * Math.log(v / b[i]) ** 2, 0));
// Average measured nucleus landmarks over several renders of a buffer factory.
const avgMeasure = (makeBuf) => {
  let acc = null;
  for (const seed of [11, 22, 33]) {
    const m = analyzeWordSample(makeBuf(seed), SR);
    if (!m.ok) return null;
    if (!acc) acc = { early: [0, 0, 0], late: [0, 0, 0], median: [0, 0, 0] };
    for (let j = 0; j < 3; j++) {
      acc.early[j] += m.nucleus.early[j] / 3;
      acc.late[j] += m.nucleus.late[j] / 3;
      acc.median[j] += m.nucleus.median[j] / 3;
    }
  }
  return acc;
};
const endpointDist = (a, b) => 0.5 * (logDist(a.early, b.early) + logDist(a.late, b.late));

// ---------------------------------------------------------------------
// 1. Calibration target list.
// Thresholds: the owner's lyrics words all appear; "frozen" carries
// the known-miss flag; a dictionary word ("the") is not flagged
// rules-only; entries expose word + reading + status.
{
  const targets = buildTargetList({ calibration: null, texts: ["Frozen flames on the water"] });
  const byWord = Object.fromEntries(targets.map(t => [t.word, t]));
  check("targets include every lyric word",
    ["frozen", "flames", "on", "the", "water"].every(w => byWord[w]),
    Object.keys(byWord).join(","));
  check("frozen flagged with the open-en known-miss pattern",
    byWord.frozen.flags.some(f => f.pattern === "open-en"));
  check("the reads from the dictionary, not rules alone", byWord.the.source === "exception");
  check("entries carry reading + uncalibrated status",
    targets.every(t => Array.isArray(t.reading) && t.status === "uncalibrated"));
  check("at least 30 probe/lyric targets listed", targets.length >= 30, String(targets.length));
}

// ---------------------------------------------------------------------
// 2. Solver recovery — injected OW offset on "goat".
// Stated tolerance: each recovered F1/F2 delta within 0.06 log of the
// injected value, F3 within 0.08 (F3 is weakly observed at this pitch:
// the synth's ninth harmonic caps the spectrum). End-to-end: the
// corrected render's endpoints measure at most half as far from the
// mock sample as the plain render's.
const INJ = [Math.log(1.18), Math.log(0.88), 0];
const mockGoat = render(["G", "OW", "T"], 52, 0.7, { offsets: { OW: { d: INJ } } });
const goat = solveWordCalibration({ calibration: null, word: "goat", mono: mockGoat, sampleRate: SR, observedTargets: [], source: "uploaded" });
check("goat sample accepted by the quality gate", !goat.refused, goat.refused || "");
check("goat produced vowel is OW", goat.produced?.ph === "OW", goat.produced?.ph);
{
  const eFrom = goat.entry.fit.dFrom.map((v, i) => Math.abs(v - INJ[i]));
  const eTo = goat.entry.fit.dTo.map((v, i) => Math.abs(v - INJ[i]));
  check("recovered dFrom within tolerance (F1/F2 <= 0.06, F3 <= 0.08)",
    eFrom[0] <= 0.06 && eFrom[1] <= 0.06 && eFrom[2] <= 0.08, eFrom.map(v => v.toFixed(3)).join("/"));
  check("recovered dTo within tolerance (F1/F2 <= 0.06, F3 <= 0.08)",
    eTo[0] <= 0.06 && eTo[1] <= 0.06 && eTo[2] <= 0.08, eTo.map(v => v.toFixed(3)).join("/"));
  const cal = resolveNoteCalibration(goat.calibration, { word: "goat", chunkIndex: 0, phonemes: ["G", "OW", "T"] });
  const smp = avgMeasure(() => mockGoat);
  const cor = avgMeasure(s => synthVocalNote({ syllable: "", phonemes: ["G", "OW", "T"], midi: 52, dur: 0.7, word: "goat", chunkIndex: 0, cal }, mulberry32(s), {}));
  const pln = avgMeasure(s => render(["G", "OW", "T"], 52, 0.7, null, s));
  const ratio = endpointDist(cor, smp) / endpointDist(pln, smp);
  check("corrected render at most half as far from the mock as plain (ratio <= 0.5)",
    ratio <= 0.5, `ratio=${ratio.toFixed(2)}`);
}

// ---------------------------------------------------------------------
// 3. Negative control — zero-offset mock.
// Stated bound: every recovered delta within 0.08 log of zero, and NO
// exception is minted (no phantom calibration).
{
  const plain = render(["G", "OW", "T"], 52, 0.7, null, 42);
  const ctl = solveWordCalibration({ calibration: null, word: "goat", mono: plain, sampleRate: SR, observedTargets: [], source: "uploaded" });
  check("control sample accepted", !ctl.refused, ctl.refused || "");
  const ds = [...(ctl.entry.fit.dFrom || []), ...(ctl.entry.fit.dTo || [])];
  check("control deltas all within 0.08 of zero", ds.every(v => Math.abs(v) <= 0.08),
    ds.map(v => v.toFixed(3)).join("/"));
  check("control mints no exception", !ctl.exception);
  check("control aggregates stay small",
    Math.abs(ctl.calibration.phonemeOffsets.OW.dFrom[0]) <= 0.08 &&
    Math.abs(ctl.calibration.phonemeOffsets.OW.dFrom[1]) <= 0.08);
}

// ---------------------------------------------------------------------
// 4. Exception minting — "frozen".
// Rule G2P reads chunk 0 as AA; the fabricated sample sings it as OW
// (stressed first syllable long, second short, as sung). Thresholds:
// the minted exception's chunk-0 nucleus is OW; the calibrated render's
// nucleus median measures at most half as far from the sample as the
// uncalibrated render's.
{
  const c0 = render(["F", "R", "OW", "Z"], 52, 0.75, null, 7);
  const c1 = render(["EH", "N"], 52, 0.3, null, 8);
  const froz = new Float32Array(c0.length + c1.length);
  froz.set(c0, 0); froz.set(c1, c0.length);
  const res = solveWordCalibration({ calibration: null, word: "frozen", mono: froz, sampleRate: SR, observedTargets: [], source: "uploaded" });
  check("frozen sample accepted", !res.refused, res.refused || "");
  check("frozen produced vowel is OW", res.produced?.ph === "OW", res.produced?.ph);
  check("exception minted with OW in chunk 0",
    !!res.exception && res.exception.phonemesByChunk[0].includes("OW"),
    JSON.stringify(res.exception?.phonemesByChunk));
  const cal = resolveNoteCalibration(res.calibration, { word: "frozen", chunkIndex: 0, phonemes: ["F", "R", "AA", "Z"] });
  check("resolved reading for frozen uses the measured phonemes",
    !!cal?.phonemes && cal.phonemes[2] === "OW", JSON.stringify(cal?.phonemes));
  const smp = avgMeasure(() => froz);
  const cor = avgMeasure(s => synthVocalNote({ syllable: "", phonemes: ["F", "R", "AA", "Z"], midi: 52, dur: 0.75, word: "frozen", chunkIndex: 0, cal }, mulberry32(s), {}));
  const pln = avgMeasure(s => render(["F", "R", "AA", "Z"], 52, 0.75, null, s));
  const ratio = logDist(cor.median, smp.median) / logDist(pln.median, smp.median);
  check("calibrated frozen nucleus at most half as far from the sample (ratio <= 0.5)",
    ratio <= 0.5, `ratio=${ratio.toFixed(2)}`);
}

// ---------------------------------------------------------------------
// 5. Transfer — the OW correction learned from "goat" must help
// "stone", a different word sharing OW, with no sample of its own.
// Threshold: transferred render's endpoint distance to the stone mock
// at most 60% of the plain render's.
{
  const mockStone = render(["S", "T", "OW", "N"], 52, 0.7, { offsets: { OW: { d: INJ } } }, 5);
  const cal = resolveNoteCalibration(goat.calibration, { word: "stone", chunkIndex: 0, phonemes: ["S", "T", "OW", "N"] });
  check("stone resolves offsets only (no track, no reading override)",
    !!cal?.offsets?.OW && !cal.track && !cal.phonemes);
  const smp = avgMeasure(() => mockStone);
  const cor = avgMeasure(s => synthVocalNote({ syllable: "", phonemes: ["S", "T", "OW", "N"], midi: 52, dur: 0.7, word: "stone", chunkIndex: 0, cal }, mulberry32(s), {}));
  const pln = avgMeasure(s => render(["S", "T", "OW", "N"], 52, 0.7, null, s));
  const ratio = endpointDist(cor, smp) / endpointDist(pln, smp);
  check("transferred correction cuts distance to at most 60% (ratio <= 0.6)",
    ratio <= 0.6, `ratio=${ratio.toFixed(2)}`);
}

// ---------------------------------------------------------------------
// 6. Quality gate — garbage is refused with a reason and writes no
// calibration data. Cases: clipped take, noise-only take, too-short
// take. Threshold: refusal + non-empty plain-language reason; after
// recording the rejection, exceptions and phoneme offsets stay empty.
{
  // An over-driven take: gain far past the rail, hard-clipped, so a
  // visible fraction of samples flat-top (a gentler push does not
  // clip this synth's mostly-quiet waveform at all).
  const loud = render(["G", "OW", "T"], 52, 0.7, null, 3).map(v => Math.max(-0.999, Math.min(0.999, v * 6)));
  const clipped = solveWordCalibration({ calibration: null, word: "goat", mono: loud, sampleRate: SR, observedTargets: [], source: "uploaded" });
  check("clipped take refused with a reason", !!clipped.refused && /clip/i.test(clipped.refused), clipped.refused || "accepted");
  const rng = mulberry32(9);
  const noise = new Float32Array(SR).map(() => (rng() * 2 - 1) * 0.4);
  const noisy = solveWordCalibration({ calibration: null, word: "goat", mono: noise, sampleRate: SR, observedTargets: [], source: "uploaded" });
  check("noise-only take refused with a reason", !!noisy.refused && noisy.refused.length > 10, noisy.refused || "accepted");
  const short = render(["AA"], 52, 0.15, null, 3);
  const tooShort = solveWordCalibration({ calibration: null, word: "ah", mono: short, sampleRate: SR, observedTargets: [], source: "uploaded" });
  check("too-short take refused with a reason", !!tooShort.refused && tooShort.refused.length > 5, tooShort.refused || "accepted");
  const after = applyRejection(null, "goat", noisy.refused);
  const sum = calibrationSummary(after);
  check("rejection stored as status, no calibration data written",
    sum.rejected === 1 && Object.keys(after.exceptions).length === 0 && Object.keys(after.phonemeOffsets).length === 0);
  check("apply functions never mutate their input",
    (() => { const before = JSON.stringify(after); applyCalibration(after, "goat", goat); return JSON.stringify(after) === before; })());
}

// ---------------------------------------------------------------------
// 7. Regression — uncalibrated rendering is V26 exactly. The pin below
// was captured from the pristine V26 tree (pre-V27) with the same
// seeds; any drift in the uncalibrated path fails here.
{
  const stats = (buf) => {
    let sum = 0, wsum = 0;
    for (let i = 0; i < buf.length; i++) { sum += buf[i]; wsum += buf[i] * i; }
    return { len: buf.length, sum, wsum, x100: buf[100], x5000: buf[5000] };
  };
  const cases = [
    { phonemes: ["HH", "AH"], midi: 57, dur: 0.5, seed: 1234, pin: { len: 22050, sum: -0.998698, wsum: -4205.329, x100: 0.02169543, x5000: -0.84924930 } },
    { phonemes: ["S", "IY"], midi: 60, dur: 0.5, seed: 99, pin: { len: 22050, sum: -31.307880, wsum: -132210.025, x100: -0.00316381, x5000: -0.03951429 } },
    { phonemes: ["N", "AY", "T"], midi: 55, dur: 0.6, seed: 7, pin: { len: 26460, sum: -16.681144, wsum: -398588.645, x100: 0.00043609, x5000: 0.01422027 } },
  ];
  for (const c of cases) {
    const s = stats(render(c.phonemes, c.midi, c.dur, null, c.seed));
    check(`V26 render pin ${c.phonemes.join("")}`,
      s.len === c.pin.len && Math.abs(s.sum - c.pin.sum) < 1e-3 && Math.abs(s.wsum - c.pin.wsum) < 1e-2 &&
      Math.abs(s.x100 - c.pin.x100) < 1e-6 && Math.abs(s.x5000 - c.pin.x5000) < 1e-6,
      JSON.stringify(s));
  }
  const wh = stats(synthVocalNote({ syllable: "", phonemes: ["HH", "AA", "R", "T"], midi: 57, dur: 0.6 }, mulberry32(77), { whisper: true }));
  check("V26 whisper render pin",
    Math.abs(wh.sum - 15.880972) < 1e-3 && Math.abs(wh.wsum - 282042.347) < 1e-2,
    JSON.stringify(wh));
  const wp = stats(synthVocalNote({ syllable: "", phonemes: ["S", "IY"], midi: 60, dur: 0.5 }, mulberry32(5), { observedTargets: [[730, 1090, 2440]] }));
  check("V26 warped render pin",
    Math.abs(wp.sum - 22.154931) < 1e-3 && Math.abs(wp.wsum - 93951.133) < 1e-2,
    JSON.stringify(wp));
}

console.log(`RESULT v27: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
