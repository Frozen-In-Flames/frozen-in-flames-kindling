// Small audio utilities: context handling, file decode, WAV encode.
// No external dependencies.

let _ctx = null;

export function getAudioContext() {
  if (!_ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    _ctx = new AC({ latencyHint: "playback" });
  }
  return _ctx;
}

export async function resumeAudio() {
  const ctx = getAudioContext();
  if (ctx.state === "suspended") {
    await ctx.resume();
  }
  return ctx;
}

// Decode without needing a user gesture: decodeAudioData works on an
// OfflineAudioContext. Returns { sampleRate, channels: [Float32Array] }.
export async function decodeFile(file) {
  const raw = await file.arrayBuffer();
  const probe = new OfflineAudioContext(1, 1, 44100);
  const decoded = await probe.decodeAudioData(raw.slice(0));
  const channels = [];
  for (let c = 0; c < decoded.numberOfChannels; c++) {
    channels.push(decoded.getChannelData(c).slice(0));
  }
  return {
    sampleRate: decoded.sampleRate,
    channels,
    duration: decoded.duration,
    name: file.name || "upload",
  };
}

export function mixdownMono(channels) {
  const n = channels[0].length;
  const out = new Float32Array(n);
  for (const ch of channels) {
    for (let i = 0; i < n; i++) out[i] += ch[i];
  }
  const k = 1 / channels.length;
  for (let i = 0; i < n; i++) out[i] *= k;
  return out;
}

export function midiToFreq(m) {
  return 440 * Math.pow(2, (m - 69) / 12);
}

export function freqToMidi(f) {
  return 69 + 12 * Math.log2(f / 440);
}

// Deterministic PRNG so the same seed renders the same choices.
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Encode planar float channels as a 16-bit PCM WAV Blob.
export function encodeWav16(channels, sampleRate) {
  const nCh = channels.length;
  const n = channels[0].length;
  const bytesPerSample = 2;
  const blockAlign = nCh * bytesPerSample;
  const dataSize = n * blockAlign;
  const buf = new ArrayBuffer(44 + dataSize);
  const v = new DataView(buf);
  const wstr = (o, s) => {
    for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i));
  };
  wstr(0, "RIFF");
  v.setUint32(4, 36 + dataSize, true);
  wstr(8, "WAVE");
  wstr(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, nCh, true);
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * blockAlign, true);
  v.setUint16(32, blockAlign, true);
  v.setUint16(34, 16, true);
  wstr(36, "data");
  v.setUint32(40, dataSize, true);
  let o = 44;
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < nCh; c++) {
      let s = channels[c][i];
      s = Math.max(-1, Math.min(1, s));
      v.setInt16(o, Math.round(s * 32767), true);
      o += 2;
    }
  }
  return new Blob([buf], { type: "audio/wav" });
}

export function audioBufferToWavBlob(audioBuffer) {
  const channels = [];
  for (let c = 0; c < audioBuffer.numberOfChannels; c++) {
    channels.push(audioBuffer.getChannelData(c));
  }
  return encodeWav16(channels, audioBuffer.sampleRate);
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 4000);
}

// Cross-platform save. The download attribute is ignored on iPhone Safari
// and awkward on some Android builds, so prefer the Web Share API with files
// when available: it opens the native share sheet (Save to Files on iOS,
// share targets on Android). Falls back to anchor download on desktop.
export async function shareOrDownloadBlob(blob, filename, extraFiles) {
  const files = [new File([blob], filename, { type: blob.type })];
  if (extraFiles) {
    for (const { blob: b, filename: fn } of extraFiles) {
      files.push(new File([b], fn, { type: b.type }));
    }
  }
  if (navigator.canShare && navigator.canShare({ files })) {
    try {
      await navigator.share({ files, title: "Frozen In Flames: Kindling" });
      return "shared";
    } catch (e) {
      if (e && e.name === "AbortError") return "cancelled";
    }
  }
  downloadBlob(blob, filename);
  if (extraFiles) {
    extraFiles.forEach(({ blob: b, filename: fn }, i) =>
      setTimeout(() => downloadBlob(b, fn), 700 * (i + 1)));
  }
  return "downloaded";
}
