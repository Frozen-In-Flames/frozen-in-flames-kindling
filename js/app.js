// Kindling web app: upload -> analyze -> save -> compose -> render -> download.
// All client-side. AudioContext is resumed on user gesture (iPhone safe).

import { resumeAudio, decodeFile, mixdownMono, audioBufferToWavBlob, shareOrDownloadBlob } from "./audio.js?v=6";
import {
  analyzePitch, analyzeVowelStates, analyzeTempo, analyzeProduction,
  detectOnsets, proposePreset, sufficiencyReport,
} from "./analysis.js?v=6";
import { saveAsset, listAssets, getAsset, renameAsset, deleteAsset, hasAsset, putRecord } from "./library.js?v=6";
import { buildScene, layoutSections, assignMelody, extractLyricsFromPrompt } from "./compose.js?v=6";
import { renderSong } from "./render.js?v=6";
import { TRACKS, newMixState, trackGain, fmtTime } from "./mixer.js?v=6";

const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));

const TABS = ["upload", "library", "compose", "updates"];

function showTab(name) {
  for (const t of TABS) {
    $("tab-" + t).classList.toggle("active", t === name);
    $("nav-" + t).classList.toggle("active", t === name);
  }
  if (name === "library") refreshLibrary();
  if (name === "compose") refreshComposeSelects();
  if (name === "updates") loadChangelog();
}

async function loadChangelog() {
  const list = $("changelog-list");
  try {
    const res = await fetch(new URL("changelog.json?v=6", document.baseURI));
    if (!res.ok) throw new Error("unavailable");
    const data = await res.json();
    const ver = $("app-version");
    if (ver && data.latest) ver.textContent = `Kindling web ${data.latest}: upload, save, compose, render, download. All on this device.`;
    list.innerHTML = (data.entries || []).map(e => `
      <div class="asset">
        <div class="ahead"><span class="badge voice">${escapeHtml(e.version)}</span><span class="dim">${escapeHtml(e.date || "")}</span></div>
        <div class="adetail">${(e.changes || []).map(c => `&bull; ${escapeHtml(c)}`).join("<br>")}</div>
      </div>`).join("") || `<p class="dim">No updates listed yet.</p>`;
  } catch (err) {
    list.innerHTML = `<p class="dim">Changelog unavailable offline. Your library and renders still work.</p>`;
  }
}

let pendingAnalysis = null;

function setStatus(el, msg, kind = "") {
  el.textContent = msg;
  el.className = "status " + kind;
}

async function yieldUi() { await sleep(10); }

async function analyzeUpload() {
  const file = $("file").files[0];
  const kind = $("kind").value;
  const name = $("aname").value.trim() || (file ? file.name.replace(/\.[^.]+$/, "") : "untitled");
  const status = $("upload-status");
  if (!file) { setStatus(status, "Pick an audio file first.", "err"); return; }
  setStatus(status, "Decoding audio...");
  await yieldUi();
  let decoded;
  try {
    decoded = await decodeFile(file);
  } catch (e) {
    setStatus(status, "Could not decode that file. Try WAV, MP3, or M4A.", "err");
    return;
  }
  const mono = mixdownMono(decoded.channels);
  const sr = decoded.sampleRate;
  setStatus(status, "Tracking pitch...");
  await yieldUi();
  const pitch = analyzePitch(mono, sr);
  setStatus(status, "Mapping vowel states...");
  await yieldUi();
  const vowels = analyzeVowelStates(mono, sr, pitch.voicedSeconds);
  setStatus(status, "Estimating tempo and production...");
  await yieldUi();
  const tempo = analyzeTempo(mono, sr);
  const prod = analyzeProduction(mono, sr, decoded.channels);
  const onsets = detectOnsets(mono, sr);
  const result = { pitch, vowels, tempo, prod, onsets };
  pendingAnalysis = { decoded, kind, name, result };
  renderAnalysisResult(result, kind, decoded);
  setStatus(status, "Analysis complete. Review, then save.", "ok");
  $("save-btn").disabled = false;
}

function fmtRegs(pitch) {
  return pitch.registers
    .filter(r => r.seconds_observed > 0.2)
    .map(r => `${r.name} ${r.seconds_observed}s (rel ${r.reliability})`)
    .join(", ") || "none with enough material";
}

function renderAnalysisResult(r, kind, decoded) {
  const box = $("analysis-result");
  const rows = [
    ["File", `${decoded.name}, ${Math.round(decoded.duration)}s, ${decoded.sampleRate} Hz, ${decoded.channels.length} ch`],
    ["Pitch range", `${r.pitch.pitchLowMidi} to ${r.pitch.pitchHighMidi} MIDI (mean ${r.pitch.pitchMean})`],
    ["Voiced material", `${r.pitch.voicedSeconds}s`],
    ["Registers", fmtRegs(r.pitch)],
    ["Vowel states", `${r.vowels.vowelCount} distinct (${r.vowels.labels.join(", ") || "none"})`],
    ["Tempo", `${r.tempo.bpm} BPM`],
    ["Tonal balance", `sub ${r.prod.tonal.sub}, low ${r.prod.tonal.low}, mid ${r.prod.tonal.mid}, high ${r.prod.tonal.high}, air ${r.prod.tonal.air}`],
    ["Dynamics", `crest ${r.prod.crestDb} dB, peak ${r.prod.peakDbfs} dBFS`],
    ["Stereo", `correlation ${r.prod.stereoCorrelation}`],
    ["Space", `ratio ${r.prod.spaceRatio}`],
    ["Onsets", `${r.onsets.length} detected`],
  ];
  box.innerHTML = rows.map(([k, v]) => `<div class="arow"><span>${k}</span><b>${v}</b></div>`).join("");
  if (kind === "voice") {
    const rep = sufficiencyReport(r.pitch, r.vowels, {});
    const verdict = rep.sufficient
      ? "SUFFICIENT: this reference can ground a voice character."
      : "GAPS: " + rep.gaps.join("; ") + " | Options: " + rep.options.join("; ");
    box.innerHTML += `<div class="arow verdict"><span>Sufficiency</span><b>${verdict}</b></div>`;
  }
  if (kind === "preset") {
    const preset = proposePreset(r.prod, "preview");
    box.innerHTML += `<div class="arow verdict"><span>Preset inference</span><b>${preset.chain.length} stages, confidence ${preset.confidence}. ${preset.disclaimer}.</b></div>`;
    box.innerHTML += preset.chain.map(fx =>
      `<div class="arow"><span>${fx.type}</span><b>${Object.entries(fx.params).map(([k, v]) => `${k}=${v}`).join(", ")}</b></div>`).join("");
  }
}

async function savePending() {
  const status = $("upload-status");
  if (!pendingAnalysis) { setStatus(status, "Analyze a file first.", "err"); return; }
  const { decoded, kind, name, result } = pendingAnalysis;
  const mono = mixdownMono(decoded.channels);
  setStatus(status, "Saving to library...");
  await yieldUi();
  let payload, consent = null;
  if (kind === "voice") {
    const subject = $("consent-subject").value.trim();
    if (!subject) { setStatus(status, "Name the voice owner for the consent record.", "err"); return; }
    consent = {
      subject, rights_basis: "consent",
      recorded_at: new Date().toISOString(),
      source: "web app self-declaration by uploader",
      verified_against_audio: true,
    };
    payload = {
      kind: "kindling/voice-character", name,
      identity: { method: "reference-deterministic-web", description: "identity from in-browser reference analysis; performance instruction is a separate input" },
      rangeMap: {
        lowMidi: result.pitch.pitchLowMidi, highMidi: result.pitch.pitchHighMidi,
        registers: result.pitch.registers,
      },
      timbre: { vowelStates: result.vowels.vowelStates },
      referenceSummary: {
        duration_s: Math.round(decoded.duration * 10) / 10,
        voiced_s: result.pitch.voicedSeconds,
        pitch_low_midi: result.pitch.pitchLowMidi,
        pitch_high_midi: result.pitch.pitchHighMidi,
        vowels_observed: result.vowels.labels,
        vowel_count: result.vowels.vowelCount,
        tempo_bpm: result.tempo.bpm,
      },
      sufficiency: sufficiencyReport(result.pitch, result.vowels, {}),
      revoked: false,
    };
  } else if (kind === "instrument") {
    const slices = [];
    const bounds = [0, ...result.onsets.filter(o => o < mono.length), mono.length];
    const maxSlices = 48;
    const step = Math.max(1, Math.floor((bounds.length - 1) / maxSlices));
    for (let i = 0; i + 1 < bounds.length && slices.length < maxSlices; i += step) {
      const s = bounds[i], e = Math.min(bounds[i + 1], s + decoded.sampleRate * 1.5);
      if (e - s < decoded.sampleRate * 0.05) continue;
      slices.push({ start: s, end: e, rootMidi: null, pcm: mono.slice(s, e) });
    }
    payload = {
      kind: "kindling/instrument", name,
      slices, sliceCount: slices.length,
      note: "Sample map sliced at detected onsets. Slices play cyclically from your recording.",
    };
  } else {
    payload = proposePreset(result.prod, name);
  }
  try {
    const rec = await saveAsset({ kind, name, payload, audioMono: mono, sampleRate: decoded.sampleRate, consent });
    setStatus(status, `Saved ${rec.id} (${rec.version}) to the library.`, "ok");
    pendingAnalysis = null;
    $("save-btn").disabled = true;
    $("file").value = "";
  } catch (e) {
    setStatus(status, "Save failed: " + e.message, "err");
  }
}

async function refreshLibrary() {
  const list = $("asset-list");
  let assets;
  try { assets = await listAssets(); }
  catch (e) { list.innerHTML = `<p class="err">Library unavailable: ${e.message}</p>`; return; }
  if (!assets.length) {
    list.innerHTML = `<p class="dim">No assets yet. Upload audio on the Upload tab to lay your first kindling.</p>`;
    return;
  }
  list.innerHTML = "";
  for (const a of assets) {
    const div = document.createElement("div");
    div.className = "asset";
    div.innerHTML = `
      <div class="ahead"><span class="badge ${a.assetKind}">${a.assetKind}</span><b>${escapeHtml(a.name)}</b><span class="dim">${a.id} ${a.version}</span></div>
      <div class="adetail">${describeAsset(a)}</div>
      <div class="arowbtns">
        <button data-act="use" data-id="${a.id}">Use in Compose</button>
        <button data-act="rename" data-id="${a.id}">Rename</button>
        <button data-act="del" data-id="${a.id}" class="danger">Delete</button>
      </div>`;
    list.appendChild(div);
  }
  list.querySelectorAll("button").forEach(b => {
    b.addEventListener("click", async () => {
      const id = b.dataset.id, act = b.dataset.act;
      if (act === "del" && confirm("Delete this asset? Its audio is removed when nothing else uses it.")) {
        await deleteAsset(id); refreshLibrary();
      } else if (act === "rename") {
        const n = prompt("New name:");
        if (n) { await renameAsset(id, n); refreshLibrary(); }
      } else if (act === "use") {
        showTab("compose"); refreshComposeSelects(id);
      }
    });
  });
}

function describeAsset(a) {
  const p = a.payload || {};
  if (a.assetKind === "voice") {
    const rs = p.referenceSummary || {};
    const suf = p.sufficiency && p.sufficiency.sufficient ? "sufficient" : "gaps";
    return `Range ${rs.pitch_low_midi} to ${rs.pitch_high_midi} MIDI, ${rs.vowel_count} vowel states, ${rs.voiced_s}s voiced. Sufficiency: ${suf}. Reference procedural voice, not a learned singing model.`;
  }
  if (a.assetKind === "instrument") {
    return `${p.sliceCount || 0} slices from onset detection. Sample map, plays from your recording.`;
  }
  const chain = (p.chain || []).map(fx => fx.type).join(", ");
  return `Chain: ${chain || "empty"}. Confidence ${p.confidence}. ${p.disclaimer || ""}`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function refreshComposeSelects(preselectId) {
  const assets = await listAssets().catch(() => []);
  const fill = (selId, kind) => {
    const sel = $(selId);
    const cur = sel.value;
    sel.innerHTML = `<option value="">(none)</option>` + assets
      .filter(a => a.assetKind === kind)
      .map(a => `<option value="${a.id}">${escapeHtml(a.name)} (${a.id})</option>`).join("");
    if (preselectId) {
      const hit = assets.find(a => a.id === preselectId && a.assetKind === kind);
      if (hit) sel.value = hit.id;
    } else if (cur) sel.value = cur;
    if (kind === "voice" && !sel.value) {
      // Default to the factory voice so it is actually used, not just saved.
      const factory = assets.find(a => a.assetKind === "voice" && a.factory);
      if (factory) sel.value = factory.id;
    }
  };
  fill("sel-voice", "voice");
  fill("sel-inst", "instrument");
  fill("sel-preset", "preset");
}

let lastRender = null;
let mixState = newMixState();
let daw = null; // active stem playback session: { ctx, sources, gains, master, startT, duration, rafId }

async function renderCompose() {
  const status = $("compose-status");
  stopPlayback();
  const prompt = $("prompt").value.trim();
  let lyrics = $("lyrics").value.trim();
  let lyricSource = "lyrics";
  if (!lyrics && prompt) {
    // Lyrics typed into the prompt field still sing: strip the production
    // directives and use the lyric-like remainder.
    lyrics = extractLyricsFromPrompt(prompt);
    if (lyrics) lyricSource = "prompt";
  }
  if (!prompt && !lyrics) { setStatus(status, "Give a prompt, lyrics, or both.", "err"); return; }
  setStatus(status, "Building scene...");
  await yieldUi();
  const seed = (Math.floor(Math.random() * 1e9)) >>> 0;
  let scene = buildScene({ prompt: prompt || "verse and chorus", lyrics, seed });
  scene = layoutSections(scene);
  const melody = assignMelody(scene, seed);
  setStatus(status, "Loading assets...");
  await yieldUi();
  const assets = {};
  const vId = $("sel-voice").value, iId = $("sel-inst").value, pId = $("sel-preset").value;
  if (vId) { const rec = await getAsset(vId); assets.voice = { id: vId, ...rec.payload }; }
  if (iId) {
    const rec = await getAsset(iId);
    assets.instrument = { id: iId, slices: rec.payload.slices || [] };
  }
  if (pId) { const rec = await getAsset(pId); assets.preset = rec.payload; }
  if (!melody.length) {
    const vname = vId ? " (voice selected but silent)" : "";
    setStatus(status, `No lyrics detected${vname}: rendering an instrumental. Type lyrics, one per line, to hear the voice.`);
  } else if (lyricSource === "prompt") {
    setStatus(status, "No lyrics-box text: singing the lyric-like words from your prompt. For full control, put lyrics in the Lyrics box.");
  } else {
    setStatus(status, "Rendering audio (offline)...");
  }
  await yieldUi();
  try {
    const t0 = performance.now();
    const result = await renderSong({ scene, melody, assets, seed });
    const ms = Math.round(performance.now() - t0);
    lastRender = { ...result, scene, seed };
    buildTimeline(scene);
    $("session-setup").open = false;
    setStatus(status, `Rendered ${Math.round(scene.totalSeconds)}s in ${ms}ms. Seed ${seed}.`, "ok");
    $("player-wrap").style.display = "block";
    $("dl-mix").disabled = false;
    $("dl-stems").disabled = false;
    const meta = result.meta;
    $("render-meta").innerHTML =
      `Voice: <b>${escapeHtml(meta.voiceId)}</b> (reference procedural voice, not a learned singing model)<br>` +
      `Instrument: <b>${escapeHtml(meta.instrumentId)}</b><br>` +
      `Preset: <b>${meta.presetApplied ? "applied" : "none"}</b>${meta.presetConfidence != null ? ` (confidence ${meta.presetConfidence})` : ""}<br>` +
      `<span class="dim">${escapeHtml(meta.honesty)}</span>`;
  } catch (e) {
    setStatus(status, "Render failed: " + e.message, "err");
  }
}

// ---- DAW: timeline regions, stem playback through a live mixer ----
function buildTimeline(scene) {
  const total = scene.totalSeconds;
  const lanes = { voice: $("tl-voice"), instruments: $("tl-inst"), drums: $("tl-drums") };
  for (const lane of Object.values(lanes)) lane.innerHTML = "";
  scene.sections.forEach((sec, i) => {
    const left = (sec.startAt / total) * 100;
    const width = ((sec.bars * scene.secondsPerBar) / total) * 100;
    for (const lane of Object.values(lanes)) {
      const r = document.createElement("div");
      r.className = "tl-region " + (i % 2 ? "ice" : "ember");
      r.style.left = left + "%";
      r.style.width = "calc(" + Math.max(0, width).toFixed(3) + "% - 2px)";
      r.textContent = sec.name;
      r.title = `${sec.name}: ${sec.bars} bars`;
      lane.appendChild(r);
    }
  });
  $("tp-bpm").textContent = scene.bpm + " BPM";
  $("tp-time").textContent = "0:00 / " + fmtTime(total);
  $("tl-playhead").style.left = "0%";
  $("timeline").style.display = "block";
  $("mixer").style.display = "flex";
  $("play-btn").disabled = false;
  $("tp-stop").disabled = true;
}

function liveMix() {
  if (!daw) return;
  for (const t of TRACKS) {
    daw.gains[t].gain.setTargetAtTime(trackGain(mixState, t), daw.ctx.currentTime, 0.02);
  }
}

function stopPlayback() {
  if (daw) {
    const d = daw;
    daw = null;
    cancelAnimationFrame(d.rafId);
    try { for (const s of d.sources) { try { s.stop(); } catch (e) {} } } catch (e) {}
    try { d.master.disconnect(); } catch (e) {}
  }
  $("play-btn").disabled = !lastRender;
  $("tp-stop").disabled = true;
  if (lastRender) {
    $("tl-playhead").style.left = "0%";
    $("tp-time").textContent = "0:00 / " + fmtTime(lastRender.scene.totalSeconds);
  }
}

async function playStems() {
  if (!lastRender || daw) return;
  const ctx = await resumeAudio();
  const master = ctx.createGain();
  master.gain.value = parseFloat($("mx-master-vol").value);
  master.connect(ctx.destination);
  const gains = {}, sources = [];
  for (const t of TRACKS) {
    const src = ctx.createBufferSource();
    src.buffer = lastRender.stems[t];
    const g = ctx.createGain();
    g.gain.value = trackGain(mixState, t);
    src.connect(g);
    g.connect(master);
    src.start(0);
    sources.push(src);
    gains[t] = g;
  }
  daw = { ctx, sources, gains, master, startT: ctx.currentTime, duration: lastRender.scene.totalSeconds, rafId: 0 };
  sources[0].onended = () => { if (daw) stopPlayback(); };
  $("play-btn").disabled = true;
  $("tp-stop").disabled = false;
  tickPlayhead();
}

function tickPlayhead() {
  if (!daw) return;
  const el = daw.ctx.currentTime - daw.startT;
  const frac = Math.min(1, Math.max(0, el / daw.duration));
  $("tl-playhead").style.left = (frac * 100).toFixed(2) + "%";
  $("tp-time").textContent = fmtTime(el) + " / " + fmtTime(daw.duration);
  if (el < daw.duration) daw.rafId = requestAnimationFrame(tickPlayhead);
}

async function downloadLastMix() {
  if (!lastRender) return;
  setStatus($("compose-status"), "Preparing mix file...", "");
  await shareOrDownloadBlob(
    audioBufferToWavBlob(lastRender.mix),
    `kindling-mix-seed${lastRender.seed}.wav`
  );
  setStatus($("compose-status"), `Rendered ${Math.round(lastRender.scene.totalSeconds)}s. Seed ${lastRender.seed}.`, "ok");
}

async function downloadLastStems() {
  if (!lastRender) return;
  const { stems, seed } = lastRender;
  const main = {
    blob: audioBufferToWavBlob(stems.voice),
    filename: `kindling-stem-voice-seed${seed}.wav`,
  };
  const extras = [
    { blob: audioBufferToWavBlob(stems.instruments), filename: `kindling-stem-instruments-seed${seed}.wav` },
    { blob: audioBufferToWavBlob(stems.drums), filename: `kindling-stem-drums-seed${seed}.wav` },
  ];
  setStatus($("compose-status"), "Preparing stem files...", "");
  await shareOrDownloadBlob(main.blob, main.filename, extras);
  setStatus($("compose-status"), `Rendered ${Math.round(lastRender.scene.totalSeconds)}s. Seed ${lastRender.seed}.`, "ok");
}

// The owner's voice ships as the default character for every user, so the
// demo works even before anyone uploads anything. Users keep and add their
// own assets alongside it; seeding never touches existing records. Runs once
// per device; if the user deletes the default it stays deleted.
const SEED_FLAG = "kindling_seeded_v1";
async function seedDefaultVoice() {
  try {
    if (localStorage.getItem(SEED_FLAG)) return;
    if (await hasAsset("voice_aries")) {
      localStorage.setItem(SEED_FLAG, "1");
      return;
    }
    const res = await fetch(new URL("seeds/voice_aries.json", document.baseURI));
    if (!res.ok) return;
    const record = await res.json();
    if (!record || record.id !== "voice_aries") return;
    await putRecord(record);
    localStorage.setItem(SEED_FLAG, "1");
  } catch (e) {
    // Offline or seed unavailable: the user can still add their own.
  }
}

function wire() {
  seedDefaultVoice();
  for (const t of TABS) {
    $("nav-" + t).addEventListener("click", () => showTab(t));
  }
  $("kind").addEventListener("change", () => {
    $("consent-row").style.display = $("kind").value === "voice" ? "block" : "none";
  });
  $("analyze-btn").addEventListener("click", async () => {
    await resumeAudio().catch(() => {});
    analyzeUpload();
  });
  $("save-btn").addEventListener("click", savePending);
  $("render-btn").addEventListener("click", async () => {
    await resumeAudio().catch(() => {});
    renderCompose();
  });
  $("play-btn").addEventListener("click", async () => {
    await resumeAudio().catch(() => {});
    playStems();
  });
  $("tp-stop").addEventListener("click", () => stopPlayback());
  for (const t of TRACKS) {
    $("mx-" + t + "-vol").addEventListener("input", e => {
      mixState[t].vol = parseFloat(e.target.value);
      liveMix();
    });
    $("mx-" + t + "-mute").addEventListener("click", e => {
      mixState[t].mute = !mixState[t].mute;
      e.target.classList.toggle("on", mixState[t].mute);
      liveMix();
    });
    $("mx-" + t + "-solo").addEventListener("click", e => {
      mixState[t].solo = !mixState[t].solo;
      e.target.classList.toggle("on", mixState[t].solo);
      liveMix();
    });
  }
  $("mx-master-vol").addEventListener("input", e => {
    if (daw) daw.master.gain.setTargetAtTime(parseFloat(e.target.value), daw.ctx.currentTime, 0.02);
  });
  $("dl-mix").addEventListener("click", downloadLastMix);
  $("dl-stems").addEventListener("click", downloadLastStems);
  showTab("upload");
  refreshComposeSelects();
}

document.addEventListener("DOMContentLoaded", wire);
