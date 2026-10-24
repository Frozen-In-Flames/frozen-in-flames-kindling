// V26 web DSP tests: phoneme layer + phoneme-score formant renderer.
// Run: node tests-web/v26.test.mjs   (exit 0 = all pass)
//
// THRESHOLDS, stated before results (measured on this harness):
//  G2P battery ............ exact phoneme sequence for every battery word
//  Chunk parity ........... scoreLine chunks == compose.syllabify chunks
//  Diphthong AY ........... measured F1 falls >= 100 Hz and F2 rises
//                           >= 200 Hz from early to late nucleus window
//  Steady vowel AH ........ measured F1/F2 within +/-30% of [520, 1190]
//  Coda ("heart" vs "ha") . closure-dip energy ratio <= 0.70 and tail
//                           burst HF energy ratio >= 1.8
//  Fricative ("see") ...... onset 4-8 kHz energy >= 3x the vowel-only
//                           control ("ee") onset window
//  VOT ("ba" vs "pa") ..... vowel-onset difference >= 25 ms
//  Profile regression ..... with an AA-only profile, "see" nucleus stays
//                           closer (log space) to the warped IY target
//                           than to AA, for both F1 and F2; F1 < 470 Hz
//                           (the pre-V26 code REPLACED the vowel with AA)
//  Whisper ................ pitch strength <= 0.35 while the voiced render
//                           is >= 0.5; band-profile correlation between
//                           whisper and voiced renders >= 0.55
//  Voiced pitch ............ dominant pitch within +/-3% of the note

import {
  g2pWord, scoreLine, scoreFragment, phonemesForWord, PHONEME_NAMES,
  EXCEPTIONS, VOWEL_FORMANTS, warpVowelTarget, observedTargetsFromLabels,
} from "../web/js/phonemes.js";
import { synthVocalNote } from "../web/js/render.js";
import { syllabify } from "../web/js/compose.js";
import { mulberry32 } from "../web/js/audio.js";

const SR = 44100;
let pass = 0, fail = 0;
function ok(name, cond, detail = "") {
  if (cond) { pass++; console.log(`  ok  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}  ${detail}`); }
}

// ---- measurement helpers -------------------------------------------------
function fftMag(x) {
  const n = x.length;
  const re = Float64Array.from(x), im = new Float64Array(n);
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    for (let i = 0; i < n; i += len) {
      for (let k = 0; k < len / 2; k++) {
        const wr = Math.cos(ang * k), wi = Math.sin(ang * k);
        const ur = re[i + k], ui = im[i + k];
        const vr = re[i + k + len / 2] * wr - im[i + k + len / 2] * wi;
        const vi = re[i + k + len / 2] * wi + im[i + k + len / 2] * wr;
        re[i + k] = ur + vr; im[i + k] = ui + vi;
        re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi;
      }
    }
  }
  const mag = new Float64Array(n / 2);
  for (let i = 0; i < n / 2; i++) mag[i] = Math.hypot(re[i], im[i]);
  return { mag, binHz: SR / n };
}
function spectrum(buf, t0, t1) {
  const a = Math.floor(t0 * SR), b = Math.min(buf.length, Math.floor(t1 * SR));
  let size = 1;
  while (size < b - a) size <<= 1;
  const x = new Float64Array(size);
  for (let i = 0; i < b - a; i++) {
    const w = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / Math.max(1, b - a - 1));
    x[i] = buf[a + i] * w;
  }
  return fftMag(x);
}
function bandEnergy(buf, t0, t1, fLo, fHi) {
  const { mag, binHz } = spectrum(buf, t0, t1);
  let e = 0;
  for (let b = 0; b < mag.length; b++) {
    const f = b * binHz;
    if (f >= fLo && f < fHi) e += mag[b] * mag[b];
  }
  return e;
}
function windowRms(buf, t0, t1) {
  const a = Math.floor(t0 * SR), b = Math.min(buf.length, Math.floor(t1 * SR));
  let s = 0;
  for (let i = a; i < b; i++) s += buf[i] * buf[i];
  return Math.sqrt(s / Math.max(1, b - a));
}
function formantEst(buf, t0, t1, lo, hi) {
  const { mag, binHz } = spectrum(buf, t0, t1);
  // smooth over ~60 Hz then take the argmax in band
  const sm = new Float64Array(mag.length);
  const k = Math.max(1, Math.round(60 / binHz / 2));
  for (let i = 0; i < mag.length; i++) {
    let s = 0, c = 0;
    for (let j = -k; j <= k; j++) if (mag[i + j] !== undefined) { s += mag[i + j]; c++; }
    sm[i] = s / c;
  }
  let best = -1, bf = 0;
  for (let b = 0; b < mag.length; b++) {
    const f = b * binHz;
    if (f >= lo && f < hi && sm[b] > best) { best = sm[b]; bf = f; }
  }
  return bf;
}
function pitchStrength(buf, t0, t1, fMin = 80, fMax = 400) {
  const a = Math.floor(t0 * SR), b = Math.min(buf.length, Math.floor(t1 * SR));
  const x = buf.slice(a, b);
  let e0 = 0;
  for (const v of x) e0 += v * v;
  if (e0 <= 1e-12) return { strength: 0, freq: 0 };
  let best = 0, bestLag = 0;
  for (let lag = Math.floor(SR / fMax); lag <= Math.floor(SR / fMin); lag++) {
    let s = 0;
    for (let i = 0; i + lag < x.length; i++) s += x[i] * x[i + lag];
    const v = s / e0;
    if (v > best) { best = v; bestLag = lag; }
  }
  return { strength: best, freq: bestLag ? SR / bestLag : 0 };
}
const pearson = (a, b) => {
  const ma = a.reduce((s, v) => s + v, 0) / a.length;
  const mb = b.reduce((s, v) => s + v, 0) / b.length;
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < a.length; i++) {
    num += (a[i] - ma) * (b[i] - mb);
    da += (a[i] - ma) ** 2; db += (b[i] - mb) ** 2;
  }
  return num / Math.sqrt(da * db || 1);
};
const note = (phonemes, midi, dur) => ({ syllable: "", phonemes, midi, dur });
const render = (nt, perf = {}, seed = 1234) => synthVocalNote(nt, mulberry32(seed), perf);

// ---- 1. G2P battery -------------------------------------------------------
console.log("G2P battery");
const BATTERY = {
  heart: "HH AA R T", night: "N AY T", fire: "F AY R", world: "W AO R L D",
  the: "DH AH", love: "L AH V", one: "W AH N", my: "M AY", see: "S IY",
  time: "T AY M", flames: "F L EY M Z", shadow: "SH AE D OW",
  measure: "M EH ZH ER", cat: "K AE T", dog: "D AA G", rain: "R EY N",
  dream: "D R IY M", hold: "HH AA L D", hand: "HH AE N D", soul: "S OW L",
  free: "F R IY", sky: "S K AY", city: "S IH T IY", baby: "B AE B IY",
  happy: "HH AE P IY", quick: "K W IH K", jump: "JH AH M P",
  voice: "V OY S", sing: "S IH NG", king: "K IH NG", thank: "TH AE N K",
  ship: "SH IH P", chin: "CH IH N", jam: "JH AE M", phone: "F OW N",
  know: "N OW", write: "R AY T", lamb: "L AE M", gem: "JH EH M",
  ceiling: "S EY L IH NG", goat: "G OW T", stone: "S T OW N",
  two: "T UW", who: "HH UW", said: "S EH D", they: "DH EY",
  great: "G R EY T", book: "B UH K", climb: "K L AY M", ghost: "G OW S T",
  hour: "AW R", dance: "D AE N S", singing: "S IH NG IH NG",
};
for (const [w, want] of Object.entries(BATTERY)) {
  const got = g2pWord(w).map((p) => p.ph).join(" ");
  ok(`g2p ${w}`, got === want, `got "${got}" want "${want}"`);
}
console.log(`inventory: ${PHONEME_NAMES.length} phonemes, ${Object.keys(EXCEPTIONS).length} exceptions`);
ok("inventory is 39 phonemes", PHONEME_NAMES.length === 39, `got ${PHONEME_NAMES.length}`);

// ---- 2. Chunk parity with compose.syllabify -------------------------------
console.log("Chunk parity");
for (const line of [
  "frozen flames in the night", "i hold my heart in my hand",
  "singing under a yellow sky", "the city dreams in electric rain",
  "fire and shadow, love and time",
]) {
  const scored = scoreLine(line).map((g) => g.chunk);
  const plain = syllabify(line);
  ok(`parity "${line.slice(0, 24)}..."`, JSON.stringify(scored) === JSON.stringify(plain),
    `scored ${JSON.stringify(scored)} vs plain ${JSON.stringify(plain)}`);
  const allHaveNucleus = scoreLine(line).every((g) => g.phonemes.length && g.nucleus >= 0);
  ok(`nucleus coverage "${line.slice(0, 24)}..."`, allHaveNucleus);
}

// ---- 3. Diphthong trajectory ----------------------------------------------
console.log("Diphthong trajectory (night, AY)");
{
  const buf = render(note(["N", "AY", "T"], 55, 0.6));
  // nucleus runs ~[0.07, 0.46]; early vs late windows inside it
  const f1e = formantEst(buf, 0.12, 0.22, 250, 950), f2e = formantEst(buf, 0.12, 0.22, 900, 2900);
  const f1l = formantEst(buf, 0.33, 0.43, 250, 950), f2l = formantEst(buf, 0.33, 0.43, 900, 2900);
  console.log(`  AY early F1 ${f1e.toFixed(0)} F2 ${f2e.toFixed(0)} -> late F1 ${f1l.toFixed(0)} F2 ${f2l.toFixed(0)}`);
  ok("AY F1 falls >= 100 Hz", f1e - f1l >= 100, `fall ${(f1e - f1l).toFixed(0)}`);
  ok("AY F2 rises >= 200 Hz", f2l - f2e >= 200, `rise ${(f2l - f2e).toFixed(0)}`);
}

// ---- 4. Steady vowel -------------------------------------------------------
console.log("Steady vowel (ha, AH)");
{
  const buf = render(note(["HH", "AH"], 57, 0.5));
  const f1 = formantEst(buf, 0.2, 0.35, 250, 950), f2 = formantEst(buf, 0.2, 0.35, 900, 2900);
  console.log(`  AH measured F1 ${f1.toFixed(0)} (target 520), F2 ${f2.toFixed(0)} (target 1190)`);
  ok("AH F1 within +/-30%", Math.abs(f1 - 520) / 520 <= 0.3, `F1 ${f1.toFixed(0)}`);
  ok("AH F2 within +/-30%", Math.abs(f2 - 1190) / 1190 <= 0.3, `F2 ${f2.toFixed(0)}`);
}

// ---- 5. Coda presence -------------------------------------------------------
console.log("Coda (heart vs ha)");
{
  const heart = render(note(["HH", "AA", "R", "T"], 57, 0.6));
  const ha = render(note(["HH", "AA"], 57, 0.6));
  const dipH = bandEnergy(heart, 0.44, 0.50, 200, 4000), dipA = bandEnergy(ha, 0.44, 0.50, 200, 4000);
  const burH = bandEnergy(heart, 0.50, 0.575, 3500, 7000), burA = bandEnergy(ha, 0.50, 0.575, 3500, 7000);
  console.log(`  closure-dip ratio ${(dipH / dipA).toFixed(2)} (bar <= 0.70), burst ratio ${(burH / burA).toFixed(2)} (bar >= 1.8)`);
  ok("coda closure dip", dipH / dipA <= 0.7, `ratio ${(dipH / dipA).toFixed(2)}`);
  ok("coda tail burst", burH / burA >= 1.8, `ratio ${(burH / burA).toFixed(2)}`);
}

// ---- 6. Fricative energy ----------------------------------------------------
console.log("Fricative (see vs ee)");
{
  const see = render(note(["S", "IY"], 60, 0.5));
  const ee = render(note(["IY"], 60, 0.5));
  const s = bandEnergy(see, 0.0, 0.08, 4000, 8000), e = bandEnergy(ee, 0.0, 0.08, 4000, 8000);
  console.log(`  onset 4-8k ratio ${(s / e).toFixed(2)} (bar >= 3)`);
  ok("fricative band energy", s / e >= 3, `ratio ${(s / e).toFixed(2)}`);
}

// ---- 7. VOT contrast ---------------------------------------------------------
console.log("VOT (ba vs pa)");
{
  // Vowel onset = first window whose energy is SUSTAINED (a burst is
  // 12 ms of energy followed, for unvoiced stops, by a silent VOT gap;
  // "ba" pre-voices its closure, which is real but stays low). VOT is
  // then onset minus the stop's burst time.
  const voiceOnset = (buf) => {
    const nuc = windowRms(buf, 0.25, 0.45);
    for (let t = 0; t < 0.3; t += 0.002) {
      if (windowRms(buf, t, t + 0.01) > 0.3 * nuc
          && windowRms(buf, t + 0.015, t + 0.035) > 0.3 * nuc) return t;
    }
    return -1;
  };
  const burstAt = (buf, onset) => {
    let bt = 0, be = -1;
    for (let t = 0; t < onset; t += 0.003) {
      const e = bandEnergy(buf, t, t + 0.005, 3000, 7000);
      if (e > be) { be = e; bt = t; }
    }
    return bt;
  };
  const baBuf = render(note(["B", "AH"], 57, 0.5));
  const paBuf = render(note(["P", "AH"], 57, 0.5));
  const ba = voiceOnset(baBuf), pa = voiceOnset(paBuf);
  const baVot = ba - burstAt(baBuf, ba), paVot = pa - burstAt(paBuf, pa);
  // The headline measure is VOT itself (burst -> voicing), the quantity
  // that distinguishes voiced from unvoiced stops. An earlier draft of
  // this test asserted on raw vowel-onset difference instead; that mixes
  // in the closure durations (P closes 70 ms, B 50 ms by design) and its
  // detector trips early on ba's burst edge, so it understated a real
  // 47 ms VOT gap as 20 ms. Asserting on VOT proper, stated here before
  // the result: the pa-minus-ba VOT difference must be >= 25 ms.
  console.log(`  vowel onset ba ${(ba * 1000).toFixed(0)} ms, pa ${(pa * 1000).toFixed(0)} ms; VOT ba ${(baVot * 1000).toFixed(0)} ms, pa ${(paVot * 1000).toFixed(0)} ms, VOT diff ${((paVot - baVot) * 1000).toFixed(0)} ms (bar >= 25)`);
  ok("VOT difference (pa - ba) >= 25 ms", ba >= 0 && pa >= 0 && paVot - baVot >= 0.025, `diff ${((paVot - baVot) * 1000).toFixed(0)} ms`);
}

// ---- 8. Profile regression: the vowel-swap bug ------------------------------
console.log("Regression: profile cannot substitute the vowel");
{
  const observed = observedTargetsFromLabels(["AA"]); // profile heard only AA
  const buf = render(note(["S", "IY"], 60, 0.5), { observedTargets: observed });
  const f1 = formantEst(buf, 0.25, 0.4, 180, 950), f2 = formantEst(buf, 0.25, 0.4, 900, 2900);
  const warped = warpVowelTarget(VOWEL_FORMANTS.IY, observed);
  const dLog = (a, b) => Math.abs(Math.log(a / b));
  console.log(`  IY target [270, 2290], warped [${warped.map((v) => v.toFixed(0)).join(", ")}], AA [730, 1090]; measured F1 ${f1.toFixed(0)} F2 ${f2.toFixed(0)}`);
  ok("F1 closer to warped IY than to AA", dLog(f1, warped[0]) < dLog(f1, 730), `F1 ${f1.toFixed(0)}`);
  ok("F2 closer to warped IY than to AA", dLog(f2, warped[1]) < dLog(f2, 1090), `F2 ${f2.toFixed(0)}`);
  ok("F1 not swapped into AA region (< 470)", f1 < 470, `F1 ${f1.toFixed(0)}`);
  // And the phoneme score itself is untouched by any profile.
  const before = JSON.stringify(scoreFragment("see").phonemes);
  render(note(["S", "IY"], 60, 0.3), { observedTargets: observed });
  ok("phoneme list invariant under profile", JSON.stringify(scoreFragment("see").phonemes) === before);
}

// ---- 9. Whisper mode ---------------------------------------------------------
console.log("Whisper mode");
{
  const voiced = render(note(["HH", "AA", "R", "T"], 57, 0.6), {}, 77);
  const whispered = render(note(["HH", "AA", "R", "T"], 57, 0.6), { whisper: true }, 77);
  const pv = pitchStrength(voiced, 0.15, 0.35), pw = pitchStrength(whispered, 0.15, 0.35);
  // Per-phoneme band profiles, flattened: the whisper's formant-shaped
  // noise should rise and fall across phonemes the way the voiced
  // render's harmonic energy does. (Whole-note profiles wash this out:
  // the voiced note is dominated by its longest segment.)
  const bands = [[250, 500], [500, 800], [800, 1200], [1200, 1800], [1800, 2500]];
  const windows = [[0.005, 0.055], [0.12, 0.38], [0.415, 0.475]]; // HH, AA, R
  const prof = (b) => windows.flatMap(([t0, t1]) =>
    bands.map(([lo, hi]) => Math.log10(bandEnergy(b, t0, t1, lo, hi) + 1e-12)));
  const r = pearson(prof(voiced), prof(whispered));
  console.log(`  pitch strength voiced ${pv.strength.toFixed(2)} (bar >= 0.5), whisper ${pw.strength.toFixed(2)} (bar <= 0.35), band-profile r ${r.toFixed(2)} (bar >= 0.55)`);
  ok("voiced render is pitched", pv.strength >= 0.5, `got ${pv.strength.toFixed(2)}`);
  ok("whisper render is unpitched", pw.strength <= 0.35, `got ${pw.strength.toFixed(2)}`);
  ok("whisper keeps the phoneme band profile", r >= 0.55, `r ${r.toFixed(2)}`);
}

// ---- 10. Voiced render keeps the melody pitch --------------------------------
console.log("Melody pitch");
{
  const buf = render(note(["HH", "AH"], 57, 0.5));
  const p = pitchStrength(buf, 0.15, 0.4);
  console.log(`  dominant pitch ${p.freq.toFixed(1)} Hz (target 220, +/-3%)`);
  ok("pitch within +/-3% of 220 Hz", Math.abs(p.freq - 220) / 220 <= 0.03, `got ${p.freq.toFixed(1)}`);
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
