"""Render-from-library (Phase A): prompt + lyrics + library assets -> song.

Pipeline:
  prompt/lyrics -> interpreter -> planner -> part builder -> per-part
  rendering (reference synth, or the assigned library sample instrument)
  -> vocal lines through the library voice character -> mixer -> preset
  on the mix bus -> export bundle (mix, stems, MIDI, lyrics, sidecar).

Honest boundaries of this Phase A path (also in docs/):
- Instruments are sample-map instruments built from uploaded recordings
  (kindling.instruments.sampler), or the deterministic reference synth for
  unassigned roles. No learned instrument model.
- Vocals are the reference vocal renderer: prosody and expressive-control
  path only, not an intelligible singing voice. A learned vocal model
  plugs into the same interface.
- The preset applies to the mix bus, like a mastering chain.
"""

from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

SAMPLE_RATE = 44100

ROLE_MIX = {
    "drums": {"level_db": -3.0, "pan": 0.0},
    "bass": {"level_db": -2.0, "pan": 0.0},
    "keys": {"level_db": -5.0, "pan": -0.2},
    "guitar": {"level_db": -4.0, "pan": 0.25},
    "pad": {"level_db": -9.0, "pan": 0.0},
    "lead_vocal": {"level_db": 0.0, "pan": 0.0},
}

_PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4,
       "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9,
       "A#": 10, "Bb": 10, "B": 11}
_CHORD_RE = re.compile(r"^([A-G][#b]?)(m?)$")


def parse_chord(chord: str):
    """'Am' -> (pc 9, minor True). Raises on unparseable input."""
    m = _CHORD_RE.match(chord.strip())
    if not m:
        raise ValueError(f"cannot parse chord {chord!r}")
    root, minor = m.group(1), m.group(2) == "m"
    return _PC[root], minor


def chord_tones(chord: str, octave: int = 4) -> List[int]:
    pc, minor = parse_chord(chord)
    intervals = [0, 3, 7] if minor else [0, 4, 7]
    base = 12 * (octave + 1) + pc
    return [base + i for i in intervals]


def _section_beats(scene: Dict[str, Any], section: Dict[str, Any]):
    b0, b1 = section["bars"]
    start_beat = (b0 - 1) * 4.0
    n_bars = b1 - b0 + 1
    return start_beat, n_bars


def build_parts(scene: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn arrangement + harmony into note-bearing parts (one per role)."""
    from kindling.scene.model import make_element_meta
    harmony = {h["section"]: h["chords"] for h in scene.get("harmony", [])}
    roles: List[str] = []
    for entry in scene.get("arrangement", []):
        for role in entry["roles"]:
            if role not in roles:
                roles.append(role)
    # Merge percussion into drums; keep the supported set only.
    roles = ["drums" if r == "percussion" else r for r in roles]
    roles = [r for r in roles
             if r in ("drums", "bass", "keys", "guitar", "pad", "lead_vocal")]
    seen, ordered = set(), []
    for r in roles:
        if r not in seen:
            seen.add(r)
            ordered.append(r)

    parts = []
    for role in ordered:
        if role == "lead_vocal":
            continue  # vocals are rendered through the voice character
        notes: List[Dict[str, Any]] = []
        for section in scene["sections"]:
            start_beat, n_bars = _section_beats(scene, section)
            chords = harmony.get(section["id"], [])
            if not chords:
                continue
            for bar_i in range(n_bars):
                chord = chords[bar_i % len(chords)]["chord"]
                pc, minor = parse_chord(chord)
                bar_beat = start_beat + bar_i * 4.0
                if role == "drums":
                    for b, pitch, dur in ((0, 36, 0.3), (1, 40, 0.25),
                                          (2, 36, 0.3), (3, 40, 0.25)):
                        notes.append({"pitch": pitch,
                                      "start_beats": bar_beat + b,
                                      "duration_beats": dur, "velocity": 0.9})
                    for h in range(8):
                        notes.append({"pitch": 46,
                                      "start_beats": bar_beat + h * 0.5,
                                      "duration_beats": 0.1, "velocity": 0.5})
                elif role == "bass":
                    root = 36 + pc
                    for b in range(4):
                        notes.append({"pitch": root,
                                      "start_beats": bar_beat + b,
                                      "duration_beats": 0.9, "velocity": 0.85})
                elif role == "keys":
                    for tone in chord_tones(chord, 4):
                        notes.append({"pitch": tone,
                                      "start_beats": bar_beat,
                                      "duration_beats": 3.8, "velocity": 0.6})
                elif role == "guitar":
                    tones = chord_tones(chord, 4)
                    seq = tones + [tones[0] + 12, tones[2], tones[1] + 12,
                                   tones[1], tones[2] + 12]
                    for i, tone in enumerate(seq):
                        notes.append({"pitch": tone,
                                      "start_beats": bar_beat + i * 0.5,
                                      "duration_beats": 0.45,
                                      "velocity": 0.7})
                elif role == "pad":
                    for tone in chord_tones(chord, 3):
                        notes.append({"pitch": tone,
                                      "start_beats": bar_beat,
                                      "duration_beats": 4.0, "velocity": 0.45})
        parts.append({"id": f"part_{role}", "role": role, "notes": notes,
                      "meta": make_element_meta(source="planner",
                                                confidence=0.8,
                                                realization="symbolic")})
    return parts


def _resample_to(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return audio
    ratio = dst_rate / src_rate
    n_out = max(1, int(audio.shape[-1] * ratio))
    idx = np.linspace(0, audio.shape[-1] - 1, n_out)
    if audio.ndim == 1:
        return np.interp(idx, np.arange(audio.shape[-1]), audio)
    return np.stack([np.interp(idx, np.arange(audio.shape[-1]), ch)
                     for ch in audio])


def build_vocal_lines(scene: Dict[str, Any], voice: Dict[str, Any],
                      bpm: float) -> List[Dict[str, Any]]:
    """One aligned lyric line per section lyric, melody from the motif
    transposed into the voice's reference range."""
    from kindling.vocals.alignment import align_lyric_line
    from kindling.vocals.g2p import SUPPORTED_LANGUAGES
    lines_by_id = {ln["id"]: ln for ln in scene["lyrics"]["lines"]}
    motif = (scene.get("motifs") or [{"intervals": [0, 4, 7, 4]}])[0]["intervals"]
    pcs = [m % 12 for m in motif]
    ref = voice["range_map"]
    lo, hi = ref["low_midi"] + 1, ref["high_midi"] - 1

    def in_range(midi: float) -> float:
        while midi < lo:
            midi += 12
        while midi > hi:
            midi -= 12
        return midi

    vocal_lines = []
    for section in scene["sections"]:
        start_beat, _ = _section_beats(scene, section)
        for li, lid in enumerate(section.get("lyrics", [])):
            line = lines_by_id.get(lid)
            if not line:
                continue
            syllables = SUPPORTED_LANGUAGES["en"].phonemize(line["text"])
            if not syllables:
                continue
            notes = []
            for si in range(len(syllables)):
                midi = in_range(60 + pcs[si % len(pcs)])
                notes.append({"pitch": int(round(midi)),
                              "start_beats": si * 1.0,
                              "duration_beats": 0.95})
            aligned = align_lyric_line(line["text"], notes, "en")
            aligned["bpm"] = bpm
            aligned["start_beats_abs"] = start_beat + li * len(syllables)
            vocal_lines.append(aligned)
    return vocal_lines


def compose(prompt: str, lyrics_text: str, library,
            voice_id: str = None,
            instrument_map: Dict[str, str] = None,
            preset_id: str = None,
            profile_id: str = None,
            seed: int = 0, tier: str = "draft",
            owner: Dict[str, Any] = None,
            out_dir: str = None,
            sample_rate: int = SAMPLE_RATE) -> Dict[str, Any]:
    """Full render-from-library song build. Returns a report dict; writes
    the export bundle to out_dir when given."""
    from kindling.planning.interpreter import interpret
    from kindling.planning.planner import ReferencePlanner
    from kindling.planning.renderer import ReferenceRenderer
    from kindling.vocals.controls import default_performance
    from kindling.vocals.renderer import ReferenceVocalRenderer
    from kindling.assets.voice import render_with_character
    from kindling.library.store import LibraryVoiceStore
    from kindling.instruments.sampler import render_sample_instrument
    from kindling.mix.mixer import Mixer
    from kindling.presets.render import render_preset
    from kindling.mix.export import export_all, write_wav
    from kindling.scene.model import make_element_meta

    instrument_map = instrument_map or {}
    owner = owner or {"id": "unknown"}
    warnings: List[str] = []
    t0 = datetime.now(timezone.utc).isoformat()

    # 1. Prompt -> draft scene.
    interp = interpret(prompt, lyrics=lyrics_text)
    scene = interp["scene"]
    assumptions = interp["assumptions"]
    scene["render"]["sample_rate"] = sample_rate
    scene["render"]["seed"] = seed
    scene["render"]["tier"] = tier

    # 2. Plan (profile scope recorded; energy bias applied when present).
    profile_context = None
    if profile_id:
        prec = library.get(profile_id)
        if prec.get("asset_kind") != "profile":
            raise ValueError(f"{profile_id!r} is not a profile asset")
        payload = prec.get("payload", {})
        profile_context = {"energy_bias": float(payload.get("energy_bias", 0.0)),
                           "scope": payload.get("scope", "full catalog")}
    planned = ReferencePlanner().plan(scene, profile_context)
    scene = planned["scene"]
    planner_changes = planned["changes"]

    # 3. Parts from arrangement + harmony.
    parts = build_parts(scene)
    scene["parts"] = parts
    bpm = float(scene["timeline"]["tempo"][0]["bpm"])
    beat_s = 60.0 / bpm

    # 4. Render each part to a mono stem.
    renderer = ReferenceRenderer()
    stems_mono: Dict[str, np.ndarray] = {}
    asset_versions: Dict[str, str] = {}
    for part in parts:
        role = part["role"]
        asset_id = instrument_map.get(role)
        if asset_id:
            rec = library.get(asset_id)
            if rec.get("asset_kind") != "instrument":
                raise ValueError(f"{asset_id!r} is not an instrument asset")
            payload = rec["payload"]
            if payload.get("kind") != "kindling/sample-instrument":
                raise ValueError(
                    f"instrument {asset_id!r} is not a Phase A sample "
                    "instrument")
            audio_mono, _ = library.load_audio_mono(rec["source_audio_sha256"])
            perf_notes = [{"midi": n["pitch"],
                           "start_s": n["start_beats"] * beat_s,
                           "dur_s": n["duration_beats"] * beat_s,
                           "vel": n.get("velocity", 0.8)}
                          for n in part["notes"]]
            stem = render_sample_instrument(payload, audio_mono, perf_notes,
                                            sample_rate, seed)
            asset_versions[role] = f"{asset_id}@{rec['version']}"
        else:
            frag = {"timeline": scene["timeline"], "parts": [part],
                    "sections": [], "vocals": [],
                    "render": {"sample_rate": sample_rate}}
            out = renderer.render_fragment(frag, {}, seed, tier)["audio"]
            stereo = np.asarray(out["samples"], dtype=float)
            stem = stereo.mean(axis=1) if stereo.ndim == 2 else stereo
            for w in out.get("metadata", {}).get("warnings", []):
                if w not in warnings:
                    warnings.append(w)
        stems_mono[part["id"]] = stem.astype(np.float32)

    # 5. Vocals through the library voice character.
    voice_warnings: List[str] = []
    if voice_id:
        vstore = LibraryVoiceStore(library)
        voice = vstore.get(voice_id)
        vocal_lines = build_vocal_lines(scene, voice, bpm)
        scene["vocals"] = [{"id": "vox_lead", "voice": voice_id,
                            "lines": [ln["text"] for ln in vocal_lines],
                            "meta": make_element_meta(source="planner",
                                                      confidence=0.8,
                                                      realization="performance")}]
        vr = ReferenceVocalRenderer()
        vox = np.zeros(1, dtype=np.float32)
        perf_base = default_performance()
        vrec = library.get(voice_id)
        asset_versions["lead_vocal"] = f"{voice_id}@{vrec['version']}"
        for i, line in enumerate(vocal_lines):
            perf = dict(perf_base)
            lang = voice.get("pronunciation", {}).get("languages", [])
            if "en" in lang:
                perf["language"] = "en"
            rendered = render_with_character(vstore, voice_id, line, perf,
                                             seed + i, vr)
            samples48 = np.asarray(rendered["audio"]["samples"], dtype=float)
            if samples48.ndim == 1:
                samples48 = np.stack([samples48, samples48], axis=1)
            stereo = _resample_to(samples48.T, 48000, sample_rate)
            mono = stereo.mean(axis=0).astype(np.float32)
            start = int(line["start_beats_abs"] * beat_s * sample_rate)
            need = start + len(mono)
            if len(vox) < need:
                vox = np.pad(vox, (0, need - len(vox)))
            vox[start:start + len(mono)] += mono
            for w in rendered["metadata"].get("warnings", []):
                if w not in voice_warnings:
                    voice_warnings.append(w)
        stems_mono["vox_lead"] = vox
        scene["lyrics"]["render_notes"] = voice_warnings

    # 6. Mix.
    production = {"routing": {pid: ROLE_MIX.get(pid.replace("part_", ""),
                                                {"level_db": -6.0, "pan": 0.0})
                              for pid in stems_mono},
                  "buses": {}, "sends": [], "automation": []}
    scene["production"]["routing"] = production["routing"]
    mixer = Mixer(rate=sample_rate)
    mixed = mixer.mix(stems_mono, production)
    mix = mixed["mix"]
    mix_pre_preset = None

    # 7. Preset on the mix bus.
    if preset_id:
        rec = library.get(preset_id)
        if rec.get("asset_kind") != "preset":
            raise ValueError(f"{preset_id!r} is not a preset asset")
        chain = rec["payload"]["preset"]["chain"]
        mix_pre_preset = mix
        mix = render_preset(mix, sample_rate, {"chain": chain})
        asset_versions["preset"] = f"{preset_id}@{rec['version']}"
        warnings.append(f"preset {preset_id!r} applied to the mix bus "
                        f"({len(chain)} effects)")

    scene["render"]["asset_versions"] = asset_versions
    scene["render"]["model_versions"] = {
        "song_renderer": "reference-deterministic",
        "vocal_renderer": "reference-procedural",
        "mixer": "kindling.mix.mixer",
    }

    provenance = {
        "tool": "kindling.library.song.compose",
        "created_at": t0,
        "owner": owner.get("id"),
        "prompt": prompt,
        "assumptions": assumptions,
        "planner_changes": planner_changes,
        "seed": seed, "tier": tier,
        "profile_scope": (profile_context or {}).get("scope"),
        "voice_warnings": voice_warnings,
        "implementation_notes": [
            "instruments: sample-map instruments from uploaded recordings; "
            "unassigned roles use the deterministic reference synth",
            "vocals: reference procedural vocal renderer (prosody and "
            "expressive-control path); not an intelligible singing voice",
            "preset applied to the mix bus",
        ],
    }

    report: Dict[str, Any] = {
        "prompt": prompt, "seed": seed, "tier": tier,
        "sections": [s["type"] for s in scene["sections"]],
        "parts": [p["id"] for p in parts],
        "vocal_lines": len(scene.get("vocals", [{}])[0].get("lines", [])) if scene.get("vocals") else 0,
        "asset_versions": asset_versions,
        "assumptions": assumptions,
        "warnings": warnings,
        "mix_report": mixed["report"],
    }

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        manifest = export_all(mix, mixed["stems"], scene, out_dir,
                              rate=sample_rate, bit_depth=16,
                              target_rate=sample_rate, provenance=provenance)
        scene_path = os.path.join(out_dir, "scene.json")
        with open(scene_path, "w") as f:
            json.dump(scene, f, indent=1, default=str)
        if mix_pre_preset is not None:
            pre_path = os.path.join(out_dir, "mix_pre_preset.wav")
            write_wav(pre_path, mix_pre_preset, sample_rate, 16)
            manifest["mix_pre_preset"] = pre_path
        manifest["scene"] = scene_path
        report["manifest"] = manifest
        report["out_dir"] = out_dir

    report["provenance"] = provenance
    return report
