// Prompt + lyrics -> scene. A readable plan: tempo, key, sections with
// chord progressions, syllable-timed vocal lines. Deterministic per seed.

import { mulberry32 } from "./audio.js?v=7";
import { scoreLine } from "./phonemes.js?v=7";

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const NOTE_SEMI = { C: 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, F: 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11 };

const PROGRESSIONS = {
  dark: { minor: true, degrees: [[0, "m"], [8, "M"], [3, "M"], [10, "M"]], label: "i - VI - III - VII" },
  bright: { minor: false, degrees: [[0, "M"], [7, "M"], [9, "m"], [5, "M"]], label: "I - V - vi - IV" },
  tense: { minor: true, degrees: [[0, "m"], [10, "M"], [8, "M"], [10, "M"]], label: "i - VII - VI - VII" },
};

export function parsePrompt(prompt) {
  const p = (prompt || "").toLowerCase();
  const bpmMatch = p.match(/(\d{2,3})\s*bpm/);
  const bpm = bpmMatch ? Math.max(60, Math.min(180, parseInt(bpmMatch[1], 10))) : 96;
  let mood = "tense";
  if (/(bright|happy|uplift|summer)/.test(p)) mood = "bright";
  else if (/(dark|heavy|brood|cold)/.test(p)) mood = "dark";
  let keyMatch = p.match(/key of ([a-g][#b]?)\s*(minor|major|min|maj)?/);
  if (!keyMatch) keyMatch = p.match(/\bin ([a-g][#b]?)\s*(minor|major|min|maj)\b/);
  let tonic = "A", minor = PROGRESSIONS[mood].minor;
  if (keyMatch) {
    tonic = keyMatch[1].toUpperCase().replace("B", "B");
    const raw = keyMatch[1];
    tonic = raw.length === 1 ? raw.toUpperCase() : raw[0].toUpperCase() + raw[1];
    if (keyMatch[2]) minor = /min/.test(keyMatch[2]);
  }
  const sections = [];
  for (const s of ["intro", "verse", "pre-chorus", "chorus", "bridge", "outro"]) {
    if (p.includes(s)) sections.push(s === "pre-chorus" ? "prechorus" : s);
  }
  if (!sections.length) sections.push("verse", "chorus");
  return { bpm, mood, tonic, minor, sections };
}

// Split a lyric line into syllable-ish chunks on vowel groups.
export function syllabify(line) {
  const words = line.trim().split(/\s+/).filter(Boolean);
  const out = [];
  for (const w of words) {
    const parts = w.toLowerCase().match(/[^aeiouy]*[aeiouy]+[^aeiouy]*/g);
    if (parts && parts.length > 1) {
      // Merge tiny fragments so timing stays singable.
      let buf = "";
      for (const pt of parts) {
        buf += pt;
        if (buf.replace(/[^a-z]/g, "").length >= 3) { out.push(buf); buf = ""; }
      }
      if (buf) out.push(buf);
    } else {
      out.push(w.toLowerCase());
    }
  }
  return out.length ? out : [line.toLowerCase()];
}

function chordTones(rootMidi, quality) {
  const third = quality === "m" ? 3 : 4;
  return [rootMidi, rootMidi + third, rootMidi + 7];
}

export function buildScene({ prompt, lyrics, seed }) {
  const parsed = parsePrompt(prompt);
  const { bpm, mood, tonic, minor, sections } = parsed;
  const prog = PROGRESSIONS[mood];
  const tonicSemi = NOTE_SEMI[tonic] ?? 9;
  const tonicMidi = 45 + ((tonicSemi - 9 + 12) % 12); // near A2
  const rand = mulberry32(seed);
  const lines = (lyrics || "").split("\n").map(l => l.trim()).filter(Boolean);
  const secLen = 4; // bars per section
  const scene = {
    kind: "kindling/scene", version: "web-1",
    seed, bpm, key: `${tonic} ${minor ? "minor" : "major"}`,
    mood, progression: prog.label, sections: [],
  };
  let lineIdx = 0;
  for (const secName of sections) {
    const chords = [];
    for (let bar = 0; bar < secLen; bar++) {
      const [deg, qual] = prog.degrees[bar % prog.degrees.length];
      const root = tonicMidi + deg;
      chords.push({ bar, root, quality: qual, tones: chordTones(root, qual) });
    }
    const secLines = [];
    const wantLines = Math.max(2, Math.min(4, Math.ceil(lines.length / sections.length)));
    for (let i = 0; i < wantLines && lineIdx < lines.length; i++, lineIdx++) {
      secLines.push(lines[lineIdx]);
    }
    scene.sections.push({ name: secName, bars: secLen, chords, lyricLines: secLines });
  }
  if (!lines.length) {
    // No lyrics: instrumental scene still renders.
    for (const s of scene.sections) s.lyricLines = [];
  }
  scene.secondsPerBar = (60 / bpm) * 4;
  scene.totalSeconds = sections.length * secLen * scene.secondsPerBar;
  return scene;
}

// Recover lyric-like text from the prompt when the Lyrics box is empty:
// strip production directives (bpm, sections, mood, key) and keep the rest.
// Returns "" when nothing lyric-like remains.
export function extractLyricsFromPrompt(prompt) {
  let t = (prompt || "").toLowerCase();
  t = t.replace(/\d{2,3}\s*bpm/g, " ");
  t = t.replace(/\b(intro|verse|pre-?chorus|chorus|bridge|outro)\b/g, " ");
  t = t.replace(/\b(bright|happy|uplift(?:ing)?|summer|dark|heavy|hard|soft|slow|fast|driving|deep|brood(?:ing)?|cold|tense|chill)\b/g, " ");
  t = t.replace(/\bkey of [a-g][#b]?\b/g, " ");
  t = t.replace(/\bin [a-g][#b]?\s*(?:minor|major|min|maj)\b/g, " ");
  t = t.replace(/[,.;:!?()[\]"]+/g, " ");
  t = t.replace(/\s+/g, " ").trim();
  t = t.replace(/^(and|with|plus)\s+/g, "");
  if (t.split(" ").filter(Boolean).length < 2) return "";
  return t;
}
export function assignMelody(scene, seed) {
  const rand = mulberry32(seed ^ 0x9e37);
  const notes = [];
  for (const sec of scene.sections) {
    let cur = sec.chords[0].tones[0] + 24; // up two octaves for the voice
    for (let li = 0; li < sec.lyricLines.length; li++) {
      const chord = sec.chords[li % sec.chords.length];
      const syllables = syllabify(sec.lyricLines[li]);
      // V26: each syllable chunk also carries its phoneme score (onsets,
      // nucleus, codas) from the phoneme layer. If the scored chunks ever
      // disagree with syllabify, notes keep their text and the renderer
      // falls back to scoring the chunk directly.
      const scored = scoreLine(sec.lyricLines[li]);
      const scoredOk = scored.length === syllables.length
        && scored.every((g, gi) => g.chunk === syllables[gi]);
      const barStart = li * (scene.secondsPerBar / Math.max(1, sec.lyricLines.length));
      const sylDur = (scene.secondsPerBar / Math.max(1, sec.lyricLines.length)) / Math.max(1, syllables.length);
      syllables.forEach((syl, si) => {
        const tone = chord.tones[Math.floor(rand() * chord.tones.length)] + 24;
        const step = rand() < 0.6 ? tone : cur + (rand() < 0.5 ? -2 : 2);
        cur = Math.max(chord.tones[0] + 19, Math.min(chord.tones[0] + 31, step));
        notes.push({
          section: sec.name, syllable: syl,
          phonemes: scoredOk ? scored[si].phonemes : null,
          start: sec.startAt + barStart + si * sylDur,
          dur: sylDur * 0.92, midi: Math.round(cur),
        });
      });
    }
  }
  return notes;
}

export function layoutSections(scene) {
  let t = 0;
  for (const sec of scene.sections) {
    sec.startAt = t;
    t += sec.bars * scene.secondsPerBar;
  }
  return scene;
}
