// Real in-browser audio analysis. Mirrors the Python reference semantics:
// voiced-frame detection, autocorrelation pitch, band-energy vowel states,
// onset-based tempo, tonal balance, crest dynamics, stereo correlation,
// and a preset proposal with confidence (never the single true chain).
// Pure functions over Float32Array; no DOM here, so this is unit testable.

import { mixdownMono, freqToMidi } from "./audio.js?v=8";

// ---- FFT (iterative radix-2) ----
export function fftMag(input) {
  const n0 = input.length;
  let n = 1;
  while (n < n0) n <<= 1;
  const re = new Float64Array(n);
  const im = new Float64Array(n);
  for (let i = 0; i < n0; i++) re[i] = input[i];
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      const tr = re[i]; re[i] = re[j]; re[j] = tr;
      const ti = im[i]; im[i] = im[j]; im[j] = ti;
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    const wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cwr = 1, cwi = 0;
      for (let k = 0; k < len / 2; k++) {
        const ur = re[i + k], ui = im[i + k];
        const vr = re[i + k + len / 2] * cwr - im[i + k + len / 2] * cwi;
        const vi = re[i + k + len / 2] * cwi + im[i + k + len / 2] * cwr;
        re[i + k] = ur + vr; im[i + k] = ui + vi;
        re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi;
        const nwr = cwr * wr - cwi * wi;
        cwi = cwr * wi + cwi * wr;
        cwr = nwr;
      }
    }
  }
  const mag = new Float64Array(n / 2);
  for (let i = 0; i < n / 2; i++) mag[i] = Math.hypot(re[i], im[i]);
  return { mag, binHz: 0, n };
}

export function spectrumOf(frame, sampleRate) {
  const { mag, n } = fftMag(frame);
  return { mag, binHz: sampleRate / n };
}

function percentile(sorted, p) {
  if (!sorted.length) return 0;
  const i = Math.min(sorted.length - 1, Math.max(0, (p / 100) * (sorted.length - 1)));
  const lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

// ---- Voiced frames (mirrors Python _voiced_frames) ----
export function voicedFrames(mono, sampleRate, maxSeconds = 90) {
  const limit = Math.min(mono.length, Math.floor(maxSeconds * sampleRate));
  const frameLen = 2048;
  const hop = 2048;
  const raw = [];
  let peak = 0;
  for (let s = 0; s + frameLen <= limit; s += hop) {
    let sum = 0, zc = 0, prev = mono[s];
    for (let i = s; i < s + frameLen; i++) {
      const x = mono[i];
      sum += x * x;
      if ((prev < 0 && x >= 0) || (prev >= 0 && x < 0)) zc++;
      prev = x;
    }
    const rms = Math.sqrt(sum / frameLen);
    const zcr = zc / frameLen;
    raw.push({ start: s, rms, zcr });
    if (rms > peak) peak = rms;
  }
  const voiced = raw.filter(f => f.rms > 0.05 * peak && f.zcr < 0.35);
  return { voiced, hopSeconds: hop / sampleRate, peak };
}

// ---- Pitch: normalized autocorrelation over 70..800 Hz ----
export function pitchACF(frame, sampleRate) {
  const n = frame.length;
  let mean = 0;
  for (let i = 0; i < n; i++) mean += frame[i];
  mean /= n;
  const lo = Math.max(1, Math.floor(sampleRate / 800));
  const hi = Math.min(n - 1, Math.ceil(sampleRate / 70));
  let e0 = 0;
  for (let i = 0; i < n; i++) { const d = frame[i] - mean; e0 += d * d; }
  if (e0 <= 1e-12) return null;
  let bestLag = -1, bestVal = -1;
  for (let lag = lo; lag <= hi; lag++) {
    let s = 0;
    for (let i = 0; i + lag < n; i++) s += (frame[i] - mean) * (frame[i + lag] - mean);
    const v = s / e0;
    if (v > bestVal) { bestVal = v; bestLag = lag; }
  }
  if (bestLag < 0 || bestVal < 0.45) return null;
  // Parabolic interpolation around the peak.
  return sampleRate / bestLag;
}

const REGISTERS = [
  { name: "chest", lo: 0, hi: 63 },
  { name: "mix", lo: 64, hi: 71 },
  { name: "head", lo: 72, hi: 127 },
];

export function analyzePitch(mono, sampleRate, onProgress) {
  const { voiced, hopSeconds } = voicedFrames(mono, sampleRate);
  const midis = [];
  const total = voiced.length;
  for (let i = 0; i < total; i++) {
    const f = voiced[i];
    const frame = mono.slice(f.start, f.start + 2048);
    const f0 = pitchACF(frame, sampleRate);
    if (f0) midis.push(freqToMidi(f0));
    if (onProgress && i % 64 === 0) onProgress(i / total);
  }
  const sorted = [...midis].sort((a, b) => a - b);
  const pitchLow = percentile(sorted, 2);
  const pitchHigh = percentile(sorted, 98);
  const voicedSeconds = voiced.length * hopSeconds;
  const registers = REGISTERS.map(r => {
    const inReg = midis.filter(m => m >= r.lo && m <= r.hi).length;
    const sec = inReg * hopSeconds;
    return {
      name: r.name, low_midi: r.lo, high_midi: r.hi,
      seconds_observed: Math.round(sec * 100) / 100,
      reliability: Math.round(Math.min(1, sec / 3) * 100) / 100,
    };
  });
  const mean = midis.length ? midis.reduce((a, b) => a + b, 0) / midis.length : 0;
  return {
    pitchLowMidi: Math.round(pitchLow * 10) / 10,
    pitchHighMidi: Math.round(pitchHigh * 10) / 10,
    pitchSpan: Math.round((pitchHigh - pitchLow) * 10) / 10,
    pitchMean: Math.round(mean * 10) / 10,
    voicedSeconds: Math.round(voicedSeconds * 100) / 100,
    registers,
    _midis: midis,
  };
}

// ---- Vowel-ish states: band-energy clustering (mirrors Python) ----
const VOWEL_BANDS = [[250, 800], [800, 1500], [1500, 2500], [2500, 3500]];
const VOWEL_FORMANTS = {
  IY: [270, 2290], IH: [390, 1990], EH: [530, 1840], AE: [660, 1720],
  AA: [730, 1090], AO: [570, 840], OW: [450, 1030], UW: [300, 870],
  UH: [440, 1020], AH: [520, 1190], ER: [490, 1350],
};

function bandEnergyVector(mag, binHz) {
  const v = [0, 0, 0, 0];
  let total = 0;
  for (let b = 0; b < mag.length; b++) {
    const f = b * binHz;
    if (f < 250 || f >= 3500) continue;
    total += mag[b];
    for (let i = 0; i < 4; i++) {
      if (f >= VOWEL_BANDS[i][0] && f < VOWEL_BANDS[i][1]) v[i] += mag[b];
    }
  }
  if (total <= 1e-12) return [0.25, 0.25, 0.25, 0.25];
  const out = v.map(x => x / total);
  const norm = Math.hypot(...out) || 1;
  return out.map(x => x / norm);
}

function cosine(a, b) {
  let d = 0;
  for (let i = 0; i < a.length; i++) d += a[i] * b[i];
  return d;
}

function nearestVowelLabel(vec) {
  // Nearest formant template, reported as an estimate.
  let best = "?", bestD = 1e9;
  for (const [name, [f1, f2]] of Object.entries(VOWEL_FORMANTS)) {
    const d = Math.abs(vec[0] * 500 - f1) / 500 + Math.abs(vec[1] * 1500 - f2) / 1500;
    if (d < bestD) { bestD = d; best = name; }
  }
  return best + "?";
}

export function analyzeVowelStates(mono, sampleRate, voicedSeconds) {
  const winLen = sampleRate; // 1 s windows
  const step = winLen / 2;
  const vecs = [];
  for (let s = 0; s + winLen <= mono.length && s < sampleRate * 120; s += step) {
    const frame = mono.slice(s, s + winLen);
    let rms = 0;
    for (let i = 0; i < frame.length; i += 7) rms += frame[i] * frame[i];
    rms = Math.sqrt(rms / (frame.length / 7));
    if (rms < 0.02) continue;
    const { mag, binHz } = spectrumOf(frame.slice(0, 8192), sampleRate);
    vecs.push(bandEnergyVector(mag, binHz));
  }
  const centers = [], counts = [];
  for (const v of vecs) {
    let bi = -1, bv = -1;
    for (let i = 0; i < centers.length; i++) {
      const s = cosine(v, centers[i]);
      if (s > bv) { bv = s; bi = i; }
    }
    if (bi >= 0 && bv >= 0.95) counts[bi]++;
    else { centers.push(v); counts.push(1); }
  }
  const states = centers.map((c, i) => ({ label: nearestVowelLabel(c), windows: counts[i] }));
  return {
    vowelStates: states,
    vowelCount: states.length,
    labels: [...new Set(states.map(s => s.label))],
  };
}

// ---- Tempo: spectral-flux onset envelope, autocorrelate for 60..200 BPM ----
export function analyzeTempo(mono, sampleRate) {
  const frameLen = 1024, hop = 512;
  const cap = Math.min(mono.length, sampleRate * 120);
  const flux = [];
  let prev = null;
  for (let s = 0; s + frameLen <= cap; s += hop) {
    const frame = mono.slice(s, s + frameLen);
    const { mag } = spectrumOf(frame, sampleRate);
    if (prev) {
      let f = 0;
      for (let b = 0; b < mag.length; b++) {
        const d = mag[b] - prev[b];
        if (d > 0) f += d;
      }
      flux.push(f);
    }
    prev = mag;
  }
  if (flux.length < 32) return { bpm: 100, confidence: 0 };
  const mean = flux.reduce((a, b) => a + b, 0) / flux.length;
  const env = flux.map(x => x - mean);
  const fps = sampleRate / hop;
  const lagMin = Math.floor((60 / 200) * fps);
  const lagMax = Math.ceil((60 / 60) * fps);
  let bestLag = lagMin, bestV = -1e9;
  for (let lag = lagMin; lag <= Math.min(lagMax, env.length - 1); lag++) {
    let v = 0;
    for (let i = 0; i + lag < env.length; i++) v += env[i] * env[i + lag];
    if (v > bestV) { bestV = v; bestLag = lag; }
  }
  let bpm = 60 / (bestLag / fps);
  while (bpm < 80) bpm *= 2;
  while (bpm > 180) bpm /= 2;
  return { bpm: Math.round(bpm), confidence: 0.6, _flux: flux, _fps: fps };
}

// ---- Tonal balance, dynamics, stereo, space ----
function bandEnergy(mag, binHz, lo, hi) {
  let e = 0;
  for (let b = 0; b < mag.length; b++) {
    const f = b * binHz;
    if (f >= lo && f < hi) e += mag[b] * mag[b];
  }
  return e;
}

export function analyzeProduction(mono, sampleRate, channels) {
  const cap = Math.min(mono.length, sampleRate * 60);
  const seg = mono.slice(0, cap);
  const { mag, binHz } = spectrumOf(seg.slice(0, 1 << 17), sampleRate);
  const sub = bandEnergy(mag, binHz, 20, 120);
  const low = bandEnergy(mag, binHz, 120, 400);
  const mid = bandEnergy(mag, binHz, 400, 2500);
  const high = bandEnergy(mag, binHz, 2500, 8000);
  const air = bandEnergy(mag, binHz, 8000, 20000);
  const total = sub + low + mid + high + air || 1;
  let peak = 0, sum = 0;
  for (let i = 0; i < seg.length; i++) {
    const a = Math.abs(seg[i]);
    if (a > peak) peak = a;
    sum += seg[i] * seg[i];
  }
  const rms = Math.sqrt(sum / seg.length);
  const crestDb = 20 * Math.log10((peak + 1e-9) / (rms + 1e-9));
  let stereoCorr = 1;
  if (channels.length >= 2) {
    const a = channels[0].slice(0, cap), b = channels[1].slice(0, cap);
    let ma = 0, mb = 0;
    for (let i = 0; i < a.length; i += 4) { ma += a[i]; mb += b[i]; }
    ma /= a.length / 4; mb /= b.length / 4;
    let sab = 0, saa = 0, sbb = 0;
    for (let i = 0; i < a.length; i += 4) {
      const da = a[i] - ma, db = b[i] - mb;
      sab += da * db; saa += da * da; sbb += db * db;
    }
    stereoCorr = sab / (Math.sqrt(saa * sbb) + 1e-12);
  }
  // Space estimate: sustained (high RMS, low flux) vs transient energy.
  const { _flux } = analyzeTempo(mono, sampleRate);
  const fluxMean = _flux.reduce((x, y) => x + y, 0) / (_flux.length || 1);
  const spaceRatio = Math.max(0, Math.min(1, 1 - fluxMean / (rms * 40 + 1e-9)));
  return {
    tonal: {
      sub: r3(sub / total), low: r3(low / total), mid: r3(mid / total),
      high: r3(high / total), air: r3(air / total),
    },
    crestDb: r3(crestDb),
    stereoCorrelation: r3(Math.max(-1, Math.min(1, stereoCorr))),
    spaceRatio: r3(spaceRatio),
    peakDbfs: r3(20 * Math.log10(peak + 1e-9)),
  };
}

function r3(x) { return Math.round(x * 1000) / 1000; }

// ---- Onset slicing for instrument sample maps ----
export function detectOnsets(mono, sampleRate) {
  const { _flux, _fps } = analyzeTempo(mono, sampleRate);
  const flux = _flux;
  const mean = flux.reduce((a, b) => a + b, 0) / flux.length;
  let sd = 0;
  for (const f of flux) sd += (f - mean) * (f - mean);
  sd = Math.sqrt(sd / flux.length);
  const thresh = mean + 1.2 * sd;
  const hop = sampleRate / _fps;
  const onsets = [];
  let last = -10;
  for (let i = 1; i < flux.length - 1; i++) {
    if (flux[i] > thresh && flux[i] >= flux[i - 1] && flux[i] >= flux[i + 1] && i - last > 4) {
      onsets.push(Math.floor(i * hop));
      last = i;
    }
  }
  return onsets;
}

// ---- Preset proposal (mirrors Python propose_preset + confidence) ----
export function proposePreset(analysis, name) {
  const tonal = analysis.tonal;
  const chain = [];
  const lowEnergy = tonal.sub + tonal.low;
  if (lowEnergy > 0.35) {
    chain.push({ type: "lowshelf", params: { freq: 200, gain_db: -Math.min(9, (lowEnergy - 0.3) * 30) } });
  } else if (lowEnergy < 0.22) {
    chain.push({ type: "lowshelf", params: { freq: 200, gain_db: Math.min(9, (0.25 - lowEnergy) * 30) } });
  }
  const highEnergy = tonal.high + tonal.air;
  if (highEnergy > 0.25) {
    chain.push({ type: "highshelf", params: { freq: 8000, gain_db: -Math.min(9, (highEnergy - 0.2) * 25) } });
  } else if (highEnergy < 0.12) {
    chain.push({ type: "highshelf", params: { freq: 8000, gain_db: Math.min(9, (0.15 - highEnergy) * 25) } });
  }
  const crest = analysis.crestDb;
  if (crest > 14) {
    chain.push({ type: "compressor", params: { threshold_db: -20, ratio: 3, attack_ms: 5, release_ms: 120 } });
  } else if (crest > 10) {
    chain.push({ type: "compressor", params: { threshold_db: -16, ratio: 2, attack_ms: 10, release_ms: 150 } });
  }
  const space = analysis.spaceRatio;
  if (space > 0.25) {
    chain.push({ type: "delay", params: { time_ms: 140, feedback: 0.35, mix: Math.min(0.5, space) } });
  }
  const corr = analysis.stereoCorrelation;
  if (corr > 0.9) chain.push({ type: "widener", params: { width: 1.3 } });
  else if (corr < 0.5) chain.push({ type: "widener", params: { width: 0.8 } });
  for (const fx of chain) {
    for (const k of Object.keys(fx.params)) {
      if (typeof fx.params[k] === "number") fx.params[k] = Math.round(fx.params[k] * 10) / 10;
    }
  }
  let score = 0.5;
  const tilt = Math.abs((tonal.sub + tonal.low) - (tonal.high + tonal.air));
  score += Math.min(0.2, tilt);
  if (crest > 14 || crest < 8) score += 0.15;
  if (corr > 0.9 || corr < 0.6) score += 0.15;
  return {
    kind: "kindling/preset",
    name,
    chain,
    targets: {
      tonal_balance: tonal, crest_db: crest,
      stereo_correlation: corr, space_ratio: space,
    },
    confidence: Math.round(Math.min(1, score) * 100) / 100,
    disclaimer: "plausible inference; different chains can produce similar audio",
  };
}

// ---- Word calibration sample measurement (V27) ----
// One take of one word. Segments voiced regions by energy, finds the
// vowel nucleus (the longest steady voiced segment), and measures its
// F1/F2/F3 track with the same spectrum machinery as the vowel states.
// The quality gate lives here: clipped, too short, too noisy, or no
// steady nucleus -> { ok: false, reason } with plain language, and the
// caller must refuse to fit anything. Never fit garbage silently.

function medianNum(arr) {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// Formant estimates for one window: energy-weighted centroids of
// tilt-compensated magnitude within ordered bands. A centroid moves
// smoothly when a formant target moves (an argmax sticks to whichever
// harmonic or skirt is loudest), which is what the calibration solver
// needs: it fits in measured space, sample against reference renders
// through this same estimator, so the estimator's bias cancels in the
// ratio instead of corrupting the fit.
function formantPeaksOf(frame, sampleRate) {
  const n = frame.length;
  const win = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const w = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / Math.max(1, n - 1));
    win[i] = frame[i] * w;
  }
  const { mag, binHz } = spectrumOf(win, sampleRate);
  const centroid = (lo, hi) => {
    let sw = 0, sf = 0;
    for (let b = 0; b < mag.length; b++) {
      const f = b * binHz;
      if (f < lo || f >= hi) continue;
      const w = mag[b] * Math.pow(f / 400, 0.8); // counter the source tilt
      sw += w; sf += w * f;
    }
    return sw > 1e-9 ? sf / sw : null;
  };
  const f1 = centroid(240, 950);
  if (f1 == null) return null;
  const f2 = centroid(Math.max(800, f1 * 1.1), 2900);
  if (f2 == null) return null;
  const f3 = centroid(Math.max(1500, f2 * 1.02), 3800);
  return [f1, f2, f3 == null ? 2400 : f3];
}

export function analyzeWordSample(mono, sampleRate) {
  const refuse = (reason) => ({ ok: false, reason });
  const dur = mono.length / sampleRate;
  if (dur < 0.2) {
    return refuse("That sample is too short to measure. Give the word a full breath, half a second or so.");
  }
  let peak = 0, clipCount = 0;
  for (let i = 0; i < mono.length; i++) {
    const a = Math.abs(mono[i]);
    if (a > peak) peak = a;
    if (a >= 0.995) clipCount++;
  }
  if (peak < 0.02) {
    return refuse("That sample is nearly silent. Move closer to the microphone and try again.");
  }
  if (clipCount / mono.length > 0.005) {
    return refuse("That take is clipped: the loudest moments hit the ceiling and flattened, so the vowels cannot be measured honestly. Lower the input level or back off the mic and try again.");
  }
  const frameLen = Math.min(2048, mono.length);
  const hop = 512;
  const frames = [];
  let peakRms = 0;
  for (let s = 0; s + frameLen <= mono.length; s += hop) {
    let sum = 0, zc = 0, prev = mono[s];
    for (let i = s; i < s + frameLen; i++) {
      const x = mono[i];
      sum += x * x;
      if ((prev < 0 && x >= 0) || (prev >= 0 && x < 0)) zc++;
      prev = x;
    }
    const rms = Math.sqrt(sum / frameLen);
    frames.push({ start: s, rms, zcr: zc / frameLen });
    if (rms > peakRms) peakRms = rms;
  }
  if (!frames.length) return refuse("That sample is too short to measure.");
  // Noise bed: measured in the frames OUTSIDE the word's energy extent
  // (the gaps before and after it). A take that is wall-to-wall voice
  // shows no bed; then this gate stays silent and the steady-nucleus
  // check below is the judge. (A percentile of all frames would mistake
  // the vowel itself for the floor on a well-filled take.)
  let firstE = -1, lastE = -1;
  frames.forEach((f, i) => {
    if (f.rms > 0.08 * peakRms) { if (firstE < 0) firstE = i; lastE = i; }
  });
  const outside = frames.filter((_, i) => i < firstE || i > lastE);
  let floor = 0;
  if (outside.length >= 3) {
    floor = medianNum(outside.map(f => f.rms));
    if (peakRms / Math.max(floor, 1e-6) < 3.5) {
      return refuse("That take is too noisy or too quiet to find a steady vowel in. A dry, close recording in a quiet room measures best.");
    }
  }
  // The voiced bar references the take's SUSTAINED level (75th
  // percentile of frame RMS), not the peak: a loud plosive or
  // fricative transient would otherwise set the bar above the vowel
  // itself and the nucleus would vanish.
  const sortedRms = frames.map(f => f.rms).sort((a, b) => a - b);
  const refLevel = sortedRms[Math.floor(0.75 * (sortedRms.length - 1))] || peakRms;
  const voicedThresh = Math.max(0.35 * refLevel, 3 * floor);
  const isVoiced = frames.map(f => f.rms > voicedThresh && f.zcr < 0.30);
  // Voiced segments: runs of voiced frames, small gaps merged.
  const segs = [];
  let cur = null;
  for (let i = 0; i < frames.length; i++) {
    if (isVoiced[i]) {
      if (!cur) cur = { a: i, b: i };
      else if (i - cur.b <= 3) cur.b = i;
      else { segs.push(cur); cur = { a: i, b: i }; }
    }
  }
  if (cur) segs.push(cur);
  const realSegs = segs.filter(s => s.b - s.a + 1 >= 3);
  const voicedSeconds = realSegs.reduce((t, s) => t + (s.b - s.a + 1), 0) * hop / sampleRate;
  if (!realSegs.length || voicedSeconds < 0.10) {
    return refuse("No steady voice was found in that take. Sing or say the word once, clearly, and hold the vowel for a beat.");
  }
  // Energy extent of the word (already located for the noise gate).
  const frameCenter = (i) => (frames[i].start + frameLen / 2) / sampleRate;
  const wordStart = frameCenter(firstE), wordEnd = frameCenter(lastE);
  // Nucleus: the longest voiced segment.
  let nuc = realSegs[0];
  for (const s of realSegs) if (s.b - s.a > nuc.b - nuc.a) nuc = s;
  const nucStartS = frames[nuc.a].start, nucEndS = frames[nuc.b].start + frameLen;
  const nucStart = nucStartS / sampleRate, nucEnd = nucEndS / sampleRate;
  // Formant track across the nucleus.
  const track = [];
  for (let s = nucStartS; s + 2048 <= nucEndS; s += hop) {
    const f = formantPeaksOf(mono.slice(s, s + 2048), sampleRate);
    if (f) track.push({ t: (s + 1024) / sampleRate - wordStart, f });
  }
  if (track.length < 3) {
    return refuse("The vowel in that take was too short to measure. Hold the word a little longer.");
  }
  // Trim edge windows: they sit on consonant transitions, not the vowel.
  const trim = Math.floor(track.length * 0.15);
  const core = track.slice(trim, track.length - trim || undefined);
  const use = core.length >= 3 ? core : track;
  const med = [0, 1, 2].map(j => medianNum(use.map(w => w.f[j])));
  const third = Math.max(1, Math.floor(use.length / 3));
  const early = [0, 1, 2].map(j => medianNum(use.slice(0, third).map(w => w.f[j])));
  const late = [0, 1, 2].map(j => medianNum(use.slice(use.length - third).map(w => w.f[j])));
  const steadyWindows = use.filter(w =>
    Math.abs(Math.log(w.f[0] / med[0])) < 0.25 && Math.abs(Math.log(w.f[1] / med[1])) < 0.25);
  const coreDur = steadyWindows.length * hop / sampleRate;
  const glide = Math.max(
    Math.abs(Math.log(early[0] / late[0])), Math.abs(Math.log(early[1] / late[1])));
  if (coreDur < 0.05 && glide <= 0.15) {
    return refuse("No steady vowel could be measured in that take: the vowel kept moving or broke up. One clean, held take of the word measures best.");
  }
  // Pitch of the nucleus (median ACF over its windows): reference
  // renders for identification and fitting are made at this pitch, so
  // the estimator sees sample and reference under the same conditions.
  const f0s = [];
  for (let s = nucStartS; s + 2048 <= nucEndS; s += hop * 2) {
    const f0 = pitchACF(mono.slice(s, s + 2048), sampleRate);
    if (f0) f0s.push(f0);
  }
  const f0 = f0s.length ? medianNum(f0s) : null;
  // Coda: what lands after the nucleus, before the word's energy ends.
  const segRms = (a, b) => {
    const x0 = Math.floor(a * sampleRate), x1 = Math.min(mono.length, Math.floor(b * sampleRate));
    if (x1 - x0 < 16) return 0;
    let s = 0;
    for (let i = x0; i < x1; i++) s += mono[i] * mono[i];
    return Math.sqrt(s / (x1 - x0));
  };
  const nucRms = segRms(nucStart, nucEnd);
  const codaDur = Math.max(0, wordEnd - nucEnd);
  const codaRatio = nucRms > 0 ? segRms(nucEnd, wordEnd) / nucRms : 0;
  return {
    ok: true,
    duration: dur,
    wordStart, wordEnd,
    wordDur: Math.max(0.05, wordEnd - wordStart),
    voicedSeconds: Math.round(voicedSeconds * 1000) / 1000,
    nucleus: {
      start: nucStart, end: nucEnd, dur: nucEnd - nucStart,
      track, median: med, early, late,
      glide: Math.round(glide * 1000) / 1000,
      steady: coreDur >= 0.05,
      f0: f0 ? Math.round(f0 * 10) / 10 : null,
    },
    onsetDur: Math.max(0, nucStart - wordStart),
    codaDur, codaRatio: Math.round(codaRatio * 1000) / 1000,
    codaPresent: codaDur > 0.025 && codaRatio > 0.04,
  };
}

// ---- Sufficiency-style report (mirrors Python sufficiency_report) ----
export function sufficiencyReport(pitch, vowels, requested) {
  const gaps = [], options = [];
  const reqLo = requested.pitchLowMidi ?? pitch.pitchLowMidi;
  const reqHi = requested.pitchHighMidi ?? pitch.pitchHighMidi;
  const pitchOk = reqLo >= pitch.pitchLowMidi - 2 && reqHi <= pitch.pitchHighMidi + 2;
  if (!pitchOk) {
    gaps.push(`requested pitch [${reqLo}, ${reqHi}] exceeds reference [${pitch.pitchLowMidi}, ${pitch.pitchHighMidi}]`);
    options.push(`transpose into [${pitch.pitchLowMidi}, ${pitch.pitchHighMidi}]`);
    options.push("record more reference material covering the missing range");
  }
  const vowelOk = vowels.vowelCount >= 4;
  if (!vowelOk) {
    gaps.push(`only ${vowels.vowelCount} distinct vowel states observed; 4+ needed`);
    options.push("record reference material with varied vowels and lyrics");
  }
  if (pitch.voicedSeconds < 3) {
    gaps.push(`only ${pitch.voicedSeconds}s of voiced reference; 3s minimum`);
    options.push("record at least 3 seconds of clean voiced singing");
  }
  return { sufficient: gaps.length === 0, gaps, options };
}
