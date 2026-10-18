// Pure mixer logic for the Compose DAW tab: solo/mute/volume resolution and
// time formatting. No DOM, no audio graph; app.js wires these to the UI.
export const TRACKS = ["voice", "instruments", "drums"];

export function newMixState() {
  const s = {};
  for (const t of TRACKS) s[t] = { vol: 0.8, mute: false, solo: false };
  return s;
}

// Standard console behavior: any active solo wins over mute.
export function trackAudible(state, t) {
  const anySolo = TRACKS.some(k => state[k] && state[k].solo);
  if (anySolo) return !!(state[t] && state[t].solo);
  return !(state[t] && state[t].mute);
}

export function trackGain(state, t) {
  return trackAudible(state, t) ? state[t].vol : 0;
}

export function fmtTime(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}
