"""Export (13.3): WAV, stems, MIDI, lyrics, sidecar.

- Mixed audio: WAV 16/24-bit, 44.1/48 kHz.
- Stems for every part and vocal, time-aligned and loudness-labeled.
- MIDI where the system can produce it reliably (from scene parts).
- Lyrics with timing.
- Sidecar: scene file, asset versions, seeds, render settings,
  provenance and watermark metadata.
"""

import json
import os
import struct
import wave
from typing import Any, Dict, List

import numpy as np

from .mixer import k_weighted_loudness


def _resample(stereo: np.ndarray, src_rate: int,
              dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return stereo
    ratio = dst_rate / src_rate
    n_out = int(stereo.shape[-1] * ratio)
    if stereo.ndim == 1:
        return np.interp(np.linspace(0, len(stereo) - 1, n_out),
                         np.arange(len(stereo)), stereo)
    return np.stack([np.interp(np.linspace(0, stereo.shape[1] - 1, n_out),
                               np.arange(stereo.shape[1]), ch)
                     for ch in stereo])


def write_wav(path: str, stereo: np.ndarray, rate: int,
              bit_depth: int = 16) -> None:
    """Write stereo WAV at 16 or 24 bit."""
    if bit_depth not in (16, 24):
        raise ValueError("bit_depth must be 16 or 24")
    # stereo shaped (2, n) or (n, 2); normalize to (n, 2).
    arr = np.asarray(stereo, dtype=float)
    if arr.ndim == 1:
        arr = np.stack([arr, arr])
    if arr.shape[0] == 2 and arr.shape[1] != 2:
        arr = arr.T
    arr = np.clip(arr, -1.0, 1.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(bit_depth // 8)
        w.setframerate(rate)
        if bit_depth == 16:
            ints = (arr * 32767).astype(np.int16)
            w.writeframes(ints.tobytes())
        else:
            ints = (arr * 8388607).astype(np.int32)
            raw = ints.tobytes()
            # Pack as 24-bit: take the top 3 bytes of each 4.
            packed = b"".join(raw[i + 1:i + 4] for i in range(0, len(raw), 4))
            w.writeframes(packed)


def export_stems(stems: Dict[str, np.ndarray], rate: int,
                 out_dir: str, bit_depth: int = 16) -> List[Dict[str, Any]]:
    """Stems, time-aligned (all start at 0) and loudness-labeled."""
    os.makedirs(out_dir, exist_ok=True)
    manifest = []
    for pid, stereo in stems.items():
        path = os.path.join(out_dir, f"stem-{pid}.wav")
        write_wav(path, stereo, rate, bit_depth)
        manifest.append({"part_id": pid, "path": path,
                         "loudness_lufs": k_weighted_loudness(stereo, rate),
                         "time_aligned": True})
    return manifest


def export_midi(scene: Dict[str, Any], path: str) -> bool:
    """MIDI from scene parts. Returns False where it cannot be produced
    reliably (no parts with notes); the caller must state this."""
    from kindling.scene.midi import scene_to_midi
    parts = [p for p in scene.get("parts", []) if p.get("notes")]
    if not parts:
        return False
    scene_to_midi(scene, path)
    return True


def export_lyrics(scene: Dict[str, Any], path: str) -> None:
    """Lyrics with timing (LRC-like)."""
    lines = scene.get("lyrics", {}).get("lines", [])
    with open(path, "w") as f:
        for i, line in enumerate(lines):
            t = line.get("start_s", i * 2.0)
            mm, ss = int(t // 60), int(t % 60)
            f.write(f"[{mm:02d}:{ss:02d}.00] {line.get('text', '')}\n")


def export_sidecar(scene: Dict[str, Any], path: str,
                   render_settings: Dict[str, Any],
                   provenance: Dict[str, Any] = None) -> None:
    """Scene file, asset versions, seeds, render settings, provenance."""
    sidecar = {
        "scene": scene,
        "asset_versions": scene.get("render", {}).get("asset_versions", {}),
        "seeds": {"render": scene.get("render", {}).get("seed", 0)},
        "render_settings": render_settings,
        "provenance": provenance or {},
    }
    with open(path, "w") as f:
        json.dump(sidecar, f, indent=1, default=str)


def export_all(mix: np.ndarray, stems: Dict[str, np.ndarray],
               scene: Dict[str, Any], out_dir: str, rate: int = 48000,
               bit_depth: int = 24,
               target_rate: int = 48000,
               provenance: Dict[str, Any] = None) -> Dict[str, Any]:
    """Full export bundle (13.3). Returns a manifest."""
    os.makedirs(out_dir, exist_ok=True)
    mix_rs = _resample(mix, rate, target_rate)
    mix_path = os.path.join(out_dir, "mix.wav")
    write_wav(mix_path, mix_rs, target_rate, bit_depth)

    stems_dir = os.path.join(out_dir, "stems")
    stem_manifest = export_stems(
        {pid: _resample(s, rate, target_rate) for pid, s in stems.items()},
        target_rate, stems_dir, bit_depth)

    midi_path = os.path.join(out_dir, "score.mid")
    midi_ok = export_midi(scene, midi_path)

    lyrics_path = os.path.join(out_dir, "lyrics.lrc")
    export_lyrics(scene, lyrics_path)

    sidecar_path = os.path.join(out_dir, "sidecar.json")
    export_sidecar(scene, sidecar_path,
                   {"sample_rate": target_rate, "bit_depth": bit_depth},
                   provenance)

    return {"mix": mix_path, "stems": stem_manifest,
            "midi": midi_path if midi_ok else None,
            "midi_note": None if midi_ok else
            "no note-bearing parts; MIDI not produced",
            "lyrics": lyrics_path, "sidecar": sidecar_path}
