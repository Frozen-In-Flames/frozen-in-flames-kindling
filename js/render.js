// Offline song renderer. Procedural reference synthesis, honest by design:
// the vocal line is a formant-textured reference voice, not a learned
// singing model. Same seed renders the same choices. Stems are pre-preset;
// the mix runs through the preset chain on the mix bus.

import { midiToFreq, mulberry32 } from "./audio.js?v=5";

const SR = 44100;

const FORMANTS = {
  AA: [730, 1090], AE: [660, 1720], AH: [520, 1190], AO: [570, 840],
  EH: [530, 1840], ER: [490, 1350], IH: [390, 1990], IY: [270, 2290],
  OW: [450, 1030], UH: [440, 1020], UW: [300, 870],
};

function vowelOf(syllable, observedLabels) {
  const m = (syllable || "").match(/[aeiouy]/);
  const natural = m ? ({ a: "AA", e: "EH", i: "IY", o: "OW", u: "UW", y: "IY" }[m[0]] || "AH") : "AH";
  if (!observedLabels || !observedLabels.length) return natural;
  const clean = observedLabels.map(l => String(l).replace(/\?$/, ""));
  if (clean.includes(natural)) return natural;
  // The synth stays inside vowels actually observed in this voice.
  return clean[0];
}

const FRICATIVES = new Set(["s", "f", "h", "z", "v", "x"]);
const STOPS = new Set(["p", "b", "t", "d", "k", "g"]);

function gauss(x) { return Math.exp(-0.5 * x * x); }

// Direct buffer synthesis of one sung syllable.
export function synthVowelNote(freq, dur, formantKey, rng, perf = {}) {
  const n = Math.max(16, Math.floor(dur * SR));
  const out = new Float32Array(n);
  const [F1, F2] = FORMANTS[formantKey] || FORMANTS.AH;
  const vibRate = perf.vibratoRateHz ?? 5.5;
  const vibDepth = perf.vibratoDepthCents != null
    ? perf.vibratoDepthCents / 100
    : (0.1 + (perf.belt || 0) * 0.12); // semitones
  let phase = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    const vib = vibDepth * Math.sin(2 * Math.PI * vibRate * t);
    const f = freq * Math.pow(2, vib / 12);
    phase += (2 * Math.PI * f) / SR;
    let s = 0, wsum = 0;
    for (let h = 1; h <= 8; h++) {
      const fh = f * h;
      const w = (1 / h) * (1 + 2 * gauss((fh - F1) / (F1 * 0.35)) + 1.4 * gauss((fh - F2) / (F2 * 0.3)));
      s += Math.sin(phase * h) * w;
      wsum += w;
    }
    out[i] = (s / (wsum || 1)) * 2.2;
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

function synthConsonant(prefix, rng) {
  // Shaped noise burst for fricatives/stops at syllable starts.
  const ch = (prefix || "").charAt(0);
  if (FRICATIVES.has(ch)) {
    const n = Math.floor(SR * 0.06);
    const out = new Float32Array(n);
    let prev = 0;
    for (let i = 0; i < n; i++) {
      const x = rng() * 2 - 1;
      const hp = x - prev; // crude highpass
      prev = x;
      out[i] = hp * (1 - i / n) * 0.5;
    }
    return out;
  }
  if (STOPS.has(ch)) {
    const n = Math.floor(SR * 0.025);
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) out[i] = (rng() * 2 - 1) * Math.exp(-i / (n * 0.25)) * 0.6;
    return out;
  }
  return null;
}

export function synthSyllable(note, rng, perf) {
  const freq = midiToFreq(note.midi);
  const vowel = synthVowelNote(freq, note.dur, vowelOf(note.syllable, perf.vowelLabels), rng, perf);
  const cons = synthConsonant(note.syllable, rng);
  if (!cons) return vowel;
  const out = new Float32Array(cons.length + vowel.length);
  out.set(cons, 0);
  for (let i = 0; i < vowel.length; i++) out[cons.length + i] += vowel[i] * 0.9;
  return out;
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
function scheduleArrangement(ctx, dest, scene, melody, assets, seed) {
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
  // Voice: syllable-timed formant synth, shaped by the selected voice profile:
  // melody fitted to its range, formants kept inside its observed vowels,
  // vibrato and belt from its performance defaults.
  const v = assets.voice || {};
  const vperf = v.performance || {};
  const perf = {
    belt: vperf.belt ?? 0.2,
    vibratoRateHz: vperf.vibratoRateHz ?? 5.5,
    vibratoDepthCents: vperf.vibratoDepthCents ?? null,
    vowelLabels: ((v.timbre && v.timbre.vowelStates) || []).map(s => s.label),
  };
  const fitted = fitMelodyToVoice(melody, v);
  for (const note of fitted) {
    const buf = synthSyllable(note, rng, perf);
    scheduleBuffer(ctx, dest.voice, buf, note.start, 0.8);
  }
}

async function renderGroups({ scene, melody, assets, seed, groups, applyChain }) {
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
    scheduleArrangement(ctx, dest, scene, melody, assets, seed);
    gVoice.gain.value = groups.voice ? 1 : 0;
    gInst.gain.value = groups.instruments ? 1 : 0;
    gDrums.gain.value = groups.drums ? 1 : 0;
  }
  return ctx.startRendering();
}

export async function renderSong({ scene, melody, assets, seed }) {
  const all = { voice: true, instruments: true, drums: true };
  const mix = await renderGroups({ scene, melody, assets, seed, groups: all, applyChain: true });
  const voice = await renderGroups({ scene, melody, assets, seed, groups: { voice: true, instruments: false, drums: false }, applyChain: false });
  const instruments = await renderGroups({ scene, melody, assets, seed, groups: { voice: false, instruments: true, drums: false }, applyChain: false });
  const drums = await renderGroups({ scene, melody, assets, seed, groups: { voice: false, instruments: false, drums: true }, applyChain: false });
  return {
    mix, stems: { voice, instruments, drums },
    meta: {
      seed,
      presetApplied: !!(assets.preset && assets.preset.chain && assets.preset.chain.length),
      presetConfidence: assets.preset ? assets.preset.confidence : null,
      voiceId: assets.voice ? assets.voice.id : "guide",
      instrumentId: assets.instrument ? assets.instrument.id : "builtin",
      honesty: "Reference procedural synthesis. The vocal line is a formant-textured reference voice, not a learned singing model. Instruments are samples or procedural tones, not learned instruments.",
    },
  };
}
