"""DAW bridge, phase one (14.4): export stems with tempo/meter maps,
import MIDI and stems. Phase two (plugin) is MAY and not built here.
"""

import json
import os
from typing import Any, Dict, List

import numpy as np

from kindling.mix import write_wav


def export_tempo_map(scene: Dict[str, Any], path: str) -> None:
    """Tempo and meter map for DAW import (bars -> bpm, meter)."""
    timeline = scene.get("timeline", {})
    tempo_map = [{"bar": t["bar"], "bpm": t["bpm"]}
                 for t in timeline.get("tempo", [])]
    meter_map = [{"bar": m["bar"], "sig": m["sig"]}
                 for m in timeline.get("meter", [])]
    with open(path, "w") as f:
        json.dump({"tempo_map": tempo_map, "meter_map": meter_map,
                   "ticks_per_beat": 480}, f, indent=1)


def export_stems_for_daw(stems: Dict[str, np.ndarray], scene: Dict[str, Any],
                         out_dir: str, rate: int = 48000) -> Dict[str, Any]:
    """Stems + tempo/meter map + a README the DAW user can follow."""
    os.makedirs(out_dir, exist_ok=True)
    for pid, audio in stems.items():
        write_wav(os.path.join(out_dir, f"{pid}.wav"), audio, rate, 24)
    export_tempo_map(scene, os.path.join(out_dir, "tempo_map.json"))
    readme = ("1. Import the WAV stems (all start at 0, 24-bit).\n"
              "2. Set your DAW to the tempo/meter map in tempo_map.json.\n"
              "3. MIDI is in score.mid where produced.\n")
    with open(os.path.join(out_dir, "README.txt"), "w") as f:
        f.write(readme)
    return {"stems": sorted(stems.keys()), "out_dir": out_dir}


def import_midi_to_scene(path: str) -> Dict[str, Any]:
    """Import a MIDI file into a scene (14.4)."""
    from kindling.scene.midi import midi_to_scene, read_midi_file
    parsed = read_midi_file(path)
    return midi_to_scene(parsed)


def import_stem(path: str) -> Dict[str, Any]:
    """Import an audio stem: returns metadata + samples path.

    The samples stay on disk (referenced, not copied into the scene).
    """
    import wave
    with wave.open(path, "rb") as w:
        meta = {"channels": w.getnchannels(), "rate": w.getframerate(),
                "frames": w.getnframes(),
                "duration_s": round(w.getnframes() / w.getframerate(), 2)}
    return {"path": path, "kind": "audio-stem", **meta}
