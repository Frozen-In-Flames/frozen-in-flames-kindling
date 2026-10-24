// Offline song renderer. Procedural reference synthesis, honest by design:
// the vocal line is phoneme-driven formant synthesis (V26), not a learned
// singing model. Same seed renders the same choices. Stems are pre-preset;
// the mix runs through the preset chain on the mix bus.

import { midiToFreq, mulberry32 } from "./audio.js?v=7";
import {
  CONSONANTS, VOWEL_FORMANTS, DIPHTHONG_FORMANTS, isVowel,
  warpVowelTarget, observedTargetsFromLabels, scoreFragment,
} from "./phonemes.js?v=7";

const SR = 44100;

function gauss(x) { return Math.exp(-0.5 * x * x); }

// ---- Vocal line: phoneme-score formant synthesis (V26) ------------------
// The score comes from phonemes.js: real English phonemes per syllable,
// fixed before any voice is chosen. Source-filter split (the owner's
// design): the words are defined by formant targets that MOVE along the
// phoneme score; the excitation is shaped noise (the whisper substrate,
// which is also how fricatives physically work) or a harmonic source at
// the melody pitch (the voiced retune). The voice profile enters only as
// warpVowelTarget: a bounded pull of targets toward its observed vowel
// space. It can shape a phoneme's sound; it can never change which
// phoneme the lyrics asked for. (The pre-V26 synth froze one vowel per
// syllable and let the profile REPLACE the lyric's vowel. Both are gone.)

function fixedDur(ph) {
  if (isVowel(ph)) return 0;
  const c = CONSONANTS[ph];
  if (!c) return 0.05;
  if (c.cls === "stop") return c.closure + 0.012 + c.vot;
  if (c.cls === "affricate") return c.closure + 0.008 + (CONSONANTS[c.fric].dur || 0.1);
  return c.dur || 0.06;
}

// Time-proportion a note: onsets and codas take their articulation times
// (scaled down together if the note is short), the nucleus takes the rest
// and carries the pitch.
function buildSegments(phonemes, totalDur) {
  const nucIdx = phonemes.findIndex(isVowel);
  let consT = 0;
  const fixed = phonemes.map((ph, idx) => {
    if (idx === nucIdx) return 0;
    const d = fixedDur(ph); consT += d; return d;
  });
  const budget = totalDur * 0.5;
  const scale = consT > budget && consT > 0 ? budget / consT : 1;
  const nucDur = Math.max(0.04, totalDur - consT * scale);
  let t = 0;
  return phonemes.map((ph, idx) => {
    const dur = idx === nucIdx ? nucDur : fixed[idx] * scale;
    const seg = { ph, info: CONSONANTS[ph] || null, start: t, dur };
    t += dur;
    return seg;
  });
}

// Formant keyframes across the note. Diphthongs get two keys (the glide);
// liquids and glides are warped like vowels; nasals keep their murmur
// targets; obstruents add no keys, so the track glides between the voiced
// neighbors around them, as a real vocal tract does.
function buildFormantTrack(segs, observed) {
  const keys = [];
  for (const seg of segs) {
    if (isVowel(seg.ph)) {
      if (DIPHTHONG_FORMANTS[seg.ph]) {
        const [a, b] = DIPHTHONG_FORMANTS[seg.ph];
        keys.push({ t: seg.start + seg.dur * 0.22, f: warpVowelTarget(a, observed) });
        keys.push({ t: seg.start + seg.dur * 0.85, f: warpVowelTarget(b, observed) });
      } else {
        keys.push({ t: seg.start + seg.dur * 0.5, f: warpVowelTarget(VOWEL_FORMANTS[seg.ph], observed) });
      }
    } else if (seg.info && seg.info.formants) {
      const warpIt = seg.info.cls === "liquid" || seg.info.cls === "glide";
      keys.push({
        t: seg.start + seg.dur * 0.5,
        f: warpIt ? warpVowelTarget(seg.info.formants, observed) : seg.info.formants.slice(),
      });
    }
  }
  if (!keys.length) keys.push({ t: 0, f: VOWEL_FORMANTS.AH.slice() });
  keys.sort((a, b) => a.t - b.t);
  return keys;
}

function trackAt(keys, t) {
  if (t <= keys[0].t) return keys[0].f;
  const last = keys[keys.length - 1];
  if (t >= last.t) return last.f;
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i], b = keys[i + 1];
    if (t >= a.t && t <= b.t) {
      let u = (t - a.t) / Math.max(1e-6, b.t - a.t);
      u = u * u * (3 - 2 * u); // smoothstep: trajectories, not steps
      return a.f.map((fa, j) => Math.exp(Math.log(fa) + u * (Math.log(b.f[j]) - Math.log(fa))));
    }
  }
  return last.f;
}

// Raw [voiceWeight, noiseWeight, noiseBand|null] for one segment at local
// time lt. This is the articulation table: closures are silent (or a low
// murmur when the stop is voiced), bursts are noise, the VOT gap is quiet,
// voiced fricatives run both sources at once, and in whisper mode every
// segment runs on noise alone through the same formant track.
function segExcitation(seg, lt, whisper) {
  const c = seg.info;
  if (isVowel(seg.ph)) return whisper ? [0, 0.85, null] : [1, 0, null];
  if (!c) return whisper ? [0, 0.5, null] : [0.6, 0, null];
  switch (c.cls) {
    case "nasal": return whisper ? [0, 0.55, null] : [c.gain, 0, null];
    case "liquid":
    case "glide": return whisper ? [0, 0.7, null] : [c.gain, 0, null];
    case "fricative": {
      const band = c.breath ? null : c.band;
      if (whisper) return [0, Math.max(0.5, c.gain), band];
      return [c.voiced ? 0.5 : 0, c.gain, band];
    }
    case "stop": {
      if (lt < c.closure) return [(!whisper && c.voiced) ? 0.22 : 0, 0, null];
      if (lt < c.closure + 0.012) return [0, c.burstGain + 0.25, c.burstBand];
      return [0, 0, null]; // voice-onset-time gap
    }
    case "affricate": {
      const fc = CONSONANTS[c.fric];
      if (lt < c.closure) return [(!whisper && c.voiced) ? 0.2 : 0, 0, null];
      if (lt < c.closure + 0.008) return [0, 0.5, fc.band];
      if (whisper) return [0, Math.max(0.5, fc.gain), fc.band];
      return [c.voiced ? 0.45 : 0, fc.gain, fc.band];
    }
    default: return [0, 0, null];
  }
}

function peaking(freq, q, gainDb) {
  const A = Math.pow(10, gainDb / 40);
  const w = (2 * Math.PI * Math.min(freq, SR * 0.45)) / SR;
  const alpha = Math.sin(w) / (2 * q), cosw = Math.cos(w);
  const b0 = 1 + alpha * A, b1 = -2 * cosw, b2 = 1 - alpha * A;
  const a0 = 1 + alpha / A, a1 = -2 * cosw, a2 = 1 - alpha / A;
  return { b: [b0 / a0, b1 / a0, b2 / a0], a1: a1 / a0, a2: a2 / a0 };
}

// Direct buffer synthesis of one sung (or whispered) syllable note.
export function synthVocalNote(note, rng, perf = {}) {
  const phonemes = (note.phonemes && note.phonemes.length)
    ? note.phonemes.slice()
    : scoreFragment(note.syllable).phonemes;
  const dur = Math.max(0.05, note.dur || 0.3);
  const n = Math.max(16, Math.floor(dur * SR));
  const out = new Float32Array(n);
  const observed = perf.observedTargets || observedTargetsFromLabels(perf.vowelLabels);
  const segs = buildSegments(phonemes.length ? phonemes : ["AH"], dur);
  const keys = buildFormantTrack(segs, observed);
  const whisper = !!perf.whisper;
  const baseFreq = midiToFreq(note.midi || 69);
  const vibRate = perf.vibratoRateHz ?? 5.5;
  const vibDepth = whisper ? 0
    : perf.vibratoDepthCents != null
      ? perf.vibratoDepthCents / 100
      : (0.1 + (perf.belt || 0) * 0.12); // semitones
  let segIdx = 0, phase = 0, voiceW = 0, noiseW = 0, prevRawNoise = 0;
  const smoothA = 1 - Math.exp(-1 / (SR * 0.003)); // ~3 ms weight smoothing
  // Two independent state sets: the formant cascade runs twice (see the
  // noise block), and each pass needs its own biquad history.
  const fstates = [{ x: [0, 0], y: [0, 0] }, { x: [0, 0], y: [0, 0] }, { x: [0, 0], y: [0, 0] },
                   { x: [0, 0], y: [0, 0] }, { x: [0, 0], y: [0, 0] }, { x: [0, 0], y: [0, 0] }];
  let fcoeffs = null, blockLeft = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    while (segIdx < segs.length - 1 && t >= segs[segIdx].start + segs[segIdx].dur) segIdx++;
    const seg = segs[segIdx];
    const [tv, tn, band] = segExcitation(seg, t - seg.start, whisper);
    voiceW += (tv - voiceW) * smoothA;
    noiseW += (tn - noiseW) * smoothA;
    const [F1, F2, F3] = trackAt(keys, t);
    const vibRamp = Math.min(1, Math.max(0, (t - 0.07) / 0.12));
    const vib = vibDepth * vibRamp * Math.sin(2 * Math.PI * vibRate * t);
    const f = baseFreq * Math.pow(2, vib / 12);
    phase += (2 * Math.PI * f) / SR;
    let voice = 0;
    if (voiceW > 0.003) {
      let s = 0, wsum = 0;
      for (let h = 1; h <= 9; h++) {
        const fh = f * h;
        if (fh > SR * 0.48) break;
        const w = (1 / h) * (1
          + 2 * gauss((fh - F1) / (F1 * 0.35))
          + 1.4 * gauss((fh - F2) / (F2 * 0.3))
          + 0.7 * gauss((fh - F3) / (F3 * 0.22)));
        s += Math.sin(phase * h) * w;
        wsum += w;
      }
      voice = (s / (wsum || 1)) * 2.2;
    }
    let noise = 0;
    if (noiseW > 0.003) {
      if (blockLeft <= 0) {
        fcoeffs = band
          ? [peaking(Math.sqrt(band[0] * band[1]), 1.1, 10), peaking(band[0], 2.5, 3), peaking(band[1], 2.5, 3)]
          : [peaking(F1, 1.3, 11), peaking(F2, 1.6, 9), peaking(F3, 2, 5)];
        blockLeft = 96;
      }
      blockLeft--;
      let x = rng() * 2 - 1;
      if (band) { const hp = x - prevRawNoise; prevRawNoise = x; x = hp; } // crude band highpass
      // Formant-shaped noise runs the cascade twice: one EQ pass leaves
      // white noise nearly flat between the formants, and a whisper's
      // identity lives in the valleys as much as the peaks.
      const passes = band ? 1 : 2;
      for (let p = 0; p < passes; p++) {
        for (let k = 0; k < 3; k++) {
          const cf = fcoeffs[k], st = fstates[p * 3 + k];
          const y = cf.b[0] * x + cf.b[1] * st.x[0] + cf.b[2] * st.x[1] - cf.a1 * st.y[0] - cf.a2 * st.y[1];
          st.x[1] = st.x[0]; st.x[0] = x; st.y[1] = st.y[0]; st.y[0] = y;
          x = y;
        }
      }
      noise = x * 1.1;
    }
    out[i] = voiceW * voice + noiseW * noise;
  }
  // Envelope: quick attack, short release.
  const atk = Math.min(n, Math.floor(SR * 0.015));
  const rel = Math.min(n, Math.floor(SR * 0.06));
  for (let i = 0; i < atk; i++) out[i] *= i / atk;
  for (let i = 0; i < rel; i++) out[n - 1 - i] *= i / rel;
  // Normalize so the voice never clips the mix bus on its own.
  let peak = 0;
  for (let i = 0; i < n; i++) peak = Math.max(peak, Math.abs(out[i]));
  if (peak > 0.85) {
    const k = 0.85 / peak;
    for (let i = 0; i < n; i++) out[i] *= k;
  }
  return out;
}

// Back-compat name: a note is one syllable of the phoneme score now.
export function synthSyllable(note, rng, perf) {
  return synthVocalNote(note, rng, perf);
}

// ---- Drums (direct synthesis) ----
function synthKick(rng) {
  const n = Math.floor(SR * 0.25);
  const out = new Float32Array(n);
  let phase = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    const f = 120 * Math.exp(-t * 30) + 40;
    phase += (2 * Math.PI * f) / SR;
    out[i] = Math.sin(phase) * Math.exp(-t * 18) * 0.9;
  }
  return out;
}
function synthSnare(rng) {
  const n = Math.floor(SR * 0.18);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    out[i] = (rng() * 2 - 1) * Math.exp(-t * 25) * 0.45 + Math.sin(2 * Math.PI * 180 * t) * Math.exp(-t * 30) * 0.3;
  }
  return out;
}
function synthHat(rng) {
  const n = Math.floor(SR * 0.05);
  const out = new Float32Array(n);
  let prev = 0;
  for (let i = 0; i < n; i++) {
    const x = rng() * 2 - 1;
    out[i] = (x - prev) * Math.exp(-i / (n * 0.2)) * 0.4;
    prev = x;
  }
  return out;
}

// ---- Built-in fallback instrument tones (when no sampled asset) ----
function synthPluck(freq, dur, rng) {
  const n = Math.max(16, Math.floor(dur * SR));
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    let s = 0;
    for (let h = 1; h <= 6; h++) s += Math.sin(2 * Math.PI * freq * h * t) / Math.pow(h, 1.5);
    out[i] = s * Math.exp(-t * 3) * 0.4;
  }
  return out;
}
function synthBass(freq, dur, rng) {
  const n = Math.max(16, Math.floor(dur * SR));
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    out[i] = (Math.sin(2 * Math.PI * freq * t) + 0.3 * Math.sin(4 * Math.PI * freq * t)) * Math.exp(-t * 1.5) * 0.55;
  }
  return out;
}

// ---- Preset chain on the mix bus ----
function buildPresetChain(ctx, preset) {
  const input = ctx.createGain();
  let node = input;
  const chain = (preset && preset.chain) || [];
  for (const fx of chain) {
    if (fx.type === "lowshelf" || fx.type === "highshelf") {
      const f = ctx.createBiquadFilter();
      f.type = fx.type === "lowshelf" ? "lowshelf" : "highshelf";
      f.frequency.value = fx.params.freq;
      f.gain.value = fx.params.gain_db;
      node.connect(f); node = f;
    } else if (fx.type === "compressor") {
      const c = ctx.createDynamicsCompressor();
      c.threshold.value = fx.params.threshold_db;
      c.ratio.value = fx.params.ratio;
      c.attack.value = fx.params.attack_ms / 1000;
      c.release.value = fx.params.release_ms / 1000;
      node.connect(c); node = c;
    } else if (fx.type === "delay") {
      const dry = ctx.createGain(); dry.gain.value = 1;
      const d = ctx.createDelay(1); d.delayTime.value = fx.params.time_ms / 1000;
      const fb = ctx.createGain(); fb.gain.value = fx.params.feedback;
      const wet = ctx.createGain(); wet.gain.value = fx.params.mix;
      node.connect(dry); node.connect(d);
      d.connect(fb); fb.connect(d); d.connect(wet);
      const sum = ctx.createGain();
      dry.connect(sum); wet.connect(sum);
      node = sum;
    } else if (fx.type === "widener") {
      const width = fx.params.width;
      const splitter = ctx.createChannelSplitter(2);
      const merger = ctx.createChannelMerger(2);
      const mid = ctx.createGain(); mid.gain.value = 0.5;
      const side = ctx.createGain(); side.gain.value = 0.5 * width;
      const sideNeg = ctx.createGain(); sideNeg.gain.value = -1;
      node.connect(splitter);
      splitter.connect(mid, 0); splitter.connect(mid, 1);
      splitter.connect(side, 0); splitter.connect(side, 1); side.connect(sideNeg);
      mid.connect(merger, 0, 0); mid.connect(merger, 0, 1);
      side.connect(merger, 0, 0); sideNeg.connect(merger, 0, 1);
      node = merger;
    }
  }
  node.connect(ctx.destination);
  return input;
}

function bufferFromMono(ctx, mono) {
  const buf = ctx.createBuffer(2, mono.length, SR);
  buf.getChannelData(0).set(mono);
  buf.getChannelData(1).set(mono);
  return buf;
}

function scheduleBuffer(ctx, dest, mono, at, gainVal = 1) {
  const src = ctx.createBufferSource();
  src.buffer = bufferFromMono(ctx, mono);
  const g = ctx.createGain();
  g.gain.value = gainVal;
  // Click-free edges.
  const n = mono.length;
  const fade = Math.min(Math.floor(SR * 0.008), Math.floor(n / 4));
  const ch0 = src.buffer.getChannelData(0), ch1 = src.buffer.getChannelData(1);
  for (let i = 0; i < fade; i++) {
    const k = i / fade;
    ch0[i] *= k; ch1[i] *= k;
    ch0[n - 1 - i] *= k; ch1[n - 1 - i] *= k;
  }
  src.connect(g); g.connect(dest);
  src.start(at);
}

function scheduleSlice(ctx, dest, slicePcm, at, rate, gainVal = 1) {
  const src = ctx.createBufferSource();
  src.buffer = bufferFromMono(ctx, slicePcm);
  src.playbackRate.value = rate;
  const g = ctx.createGain();
  g.gain.value = gainVal;
  src.connect(g); g.connect(dest);
  src.start(at);
  src.stop(at + slicePcm.length / SR / rate + 0.05);
}

function pickSlice(slices, targetMidi, idx) {
  const pitched = slices.filter(s => s.rootMidi != null);
  if (pitched.length) {
    let best = pitched[0], bd = 1e9;
    for (const s of pitched) {
      const d = Math.abs(s.rootMidi - targetMidi);
      if (d < bd) { bd = d; best = s; }
    }
    return best;
  }
  return slices[idx % slices.length];
}

// Fit the melody into the selected voice's comfortable range, by octaves,
// then clamp. A voice profile with no range map leaves the melody untouched.
function fitMelodyToVoice(melody, voice) {
  const rm = voice && voice.rangeMap;
  if (!rm || rm.lowMidi == null || rm.highMidi == null) return melody;
  const lo = rm.lowMidi, hi = rm.highMidi;
  return melody.map(n => {
    let m = n.midi, guard = 0;
    while (m < lo && guard++ < 8) m += 12;
    guard = 0;
    while (m > hi && guard++ < 8) m -= 12;
    m = Math.max(lo, Math.min(hi, m));
    return { ...n, midi: Math.round(m) };
  });
}
function scheduleArrangement(ctx, dest, scene, melody, assets, seed, whisper = false) {
  const rng = mulberry32(seed);
  const spb = 60 / scene.bpm; // seconds per beat
  const drumKit = { kick: synthKick(rng), snare: synthSnare(rng), hat: synthHat(rng) };
  const slices = (assets.instrument && assets.instrument.slices) || [];
  let sliceIdx = 0;
  const instOf = (midi, dur, at, gainVal) => {
    if (slices.length) {
      const s = pickSlice(slices, midi, sliceIdx++);
      const rate = s.rootMidi != null ? Math.pow(2, (midi - s.rootMidi) / 12) : 1;
      scheduleSlice(ctx, dest.instruments, s.pcm, at, rate, gainVal);
    } else {
      scheduleBuffer(ctx, dest.instruments, synthPluck(midiToFreq(midi), dur, rng), at, gainVal);
    }
  };
  for (const sec of scene.sections) {
    for (let bar = 0; bar < sec.bars; bar++) {
      const t0 = sec.startAt + bar * scene.secondsPerBar;
      const chord = sec.chords[bar % sec.chords.length];
      // Bass: roots on beats 1 and 3.
      for (const b of [0, 2]) {
        const at = t0 + b * spb;
        if (slices.length) instOf(chord.root - 0, spb * 1.8, at, 0.9);
        else scheduleBuffer(ctx, dest.instruments, synthBass(midiToFreq(chord.root), spb * 1.8, rng), at, 1);
      }
      // Pluck: chord tones on eighths.
      for (let e = 0; e < 8; e++) {
        const tone = chord.tones[e % chord.tones.length] + 12;
        instOf(tone, spb * 0.45, t0 + e * spb * 0.5, 0.5);
      }
      // Drums: kick 1,3 / snare 2,4 / hats eighths.
      for (let b = 0; b < 4; b++) {
        const at = t0 + b * spb;
        scheduleBuffer(ctx, dest.drums, b % 2 === 0 ? drumKit.kick : drumKit.snare, at, 0.9);
        scheduleBuffer(ctx, dest.drums, drumKit.hat, at, 0.7);
        scheduleBuffer(ctx, dest.drums, drumKit.hat, at + spb * 0.5, 0.5);
      }
    }
  }
  // Voice: phoneme-score formant synth (V26). The melody is fitted to the
  // profile's range and the formant targets are warped (bounded) toward
  // its observed vowel space, but the phonemes come from the lyrics alone.
  const v = assets.voice || {};
  const vperf = v.performance || {};
  const perf = {
    belt: vperf.belt ?? 0.2,
    vibratoRateHz: vperf.vibratoRateHz ?? 5.5,
    vibratoDepthCents: vperf.vibratoDepthCents ?? null,
    vowelLabels: ((v.timbre && v.timbre.vowelStates) || []).map(s => s.label),
    observedTargets: observedTargetsFromLabels(
      ((v.timbre && v.timbre.vowelStates) || []).map(s => s.label)),
    whisper: !!whisper,
  };
  const fitted = fitMelodyToVoice(melody, v);
  for (const note of fitted) {
    const buf = synthSyllable(note, rng, perf);
    scheduleBuffer(ctx, dest.voice, buf, note.start, 0.8);
  }
}

async function renderGroups({ scene, melody, assets, seed, groups, applyChain, whisper = false }) {
  const totalSec = scene.totalSeconds + 1.5;
  const len = Math.ceil(totalSec * SR);
  const ctx = new OfflineAudioContext(2, len, SR);
  const gVoice = ctx.createGain(), gInst = ctx.createGain(), gDrums = ctx.createGain();
  let out = ctx.destination;
  if (applyChain) {
    const chainIn = buildPresetChain(ctx, assets.preset);
    gVoice.connect(chainIn); gInst.connect(chainIn); gDrums.connect(chainIn);
  } else {
    gVoice.connect(ctx.destination); gInst.connect(ctx.destination); gDrums.connect(ctx.destination);
  }
  const dest = { voice: gVoice, instruments: gInst, drums: gDrums };
  if (groups.voice || groups.instruments || groups.drums) {
    // Schedule everything, then mute the groups we do not want.
    scheduleArrangement(ctx, dest, scene, melody, assets, seed, whisper);
    gVoice.gain.value = groups.voice ? 1 : 0;
    gInst.gain.value = groups.instruments ? 1 : 0;
    gDrums.gain.value = groups.drums ? 1 : 0;
  }
  return ctx.startRendering();
}

export async function renderSong({ scene, melody, assets, seed, whisper = false }) {
  const all = { voice: true, instruments: true, drums: true };
  const mix = await renderGroups({ scene, melody, assets, seed, groups: all, applyChain: true, whisper });
  const voice = await renderGroups({ scene, melody, assets, seed, groups: { voice: true, instruments: false, drums: false }, applyChain: false, whisper });
  const instruments = await renderGroups({ scene, melody, assets, seed, groups: { voice: false, instruments: true, drums: false }, applyChain: false, whisper });
  const drums = await renderGroups({ scene, melody, assets, seed, groups: { voice: false, instruments: false, drums: true }, applyChain: false, whisper });
  return {
    mix, stems: { voice, instruments, drums },
    meta: {
      seed,
      whisperMode: !!whisper,
      presetApplied: !!(assets.preset && assets.preset.chain && assets.preset.chain.length),
      presetConfidence: assets.preset ? assets.preset.confidence : null,
      voiceId: assets.voice ? assets.voice.id : "guide",
      instrumentId: assets.instrument ? assets.instrument.id : "builtin",
      honesty: "Reference procedural synthesis. Lyrics are converted to English phonemes and sung through moving formant filters: the words are generated in shaped noise first, then retuned to the voice profile (a bounded formant warp, phonemes unchanged), or left as a pure whisper. Not a learned singing model. Instruments are samples or procedural tones, not learned instruments.",
    },
  };
}
