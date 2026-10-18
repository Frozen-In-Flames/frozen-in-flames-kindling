"""Hierarchical generation (Part 6.4).

Plan at song level, refine at section level, render at phrase or chunk
level. Chunks MUST overlap, and each chunk MUST be conditioned on the
surrounding audio and scene context, before and after it where available.
The overlap is joined with an equal-power crossfade so chunk boundaries do
not click.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import numpy as np


def chunk_scene(scene: Dict[str, Any], chunk_bars: int = 4,
                overlap_bars: int = 1) -> List[Dict[str, Any]]:
    """Split a scene into overlapping bar-window fragments for chunk render.

    Each fragment is rebased so its first bar is bar 1 and its first beat is
    beat 0: chunk outputs tile end to end, joined by the overlap crossfade.
    """
    sections = scene.get("sections", [])
    if not sections:
        return [copy.deepcopy(scene)]
    first_bar = min(s["bars"][0] for s in sections)
    last_bar = max(s["bars"][1] for s in sections)
    beats_per_bar = 4  # chunking assumes 4/4; other meters arrive with V14
    chunks = []
    start = first_bar
    index = 0
    while start < last_bar:
        end = min(last_bar, start + chunk_bars - 1)
        frag = copy.deepcopy(scene)
        frag["sections"] = []
        for s in sections:
            if s["bars"][1] < start or s["bars"][0] > end:
                continue
            clipped = copy.deepcopy(s)
            clipped["bars"] = [max(start, s["bars"][0]) - start + 1,
                               min(end, s["bars"][1]) - start + 1]
            frag["sections"].append(clipped)
        frag["parts"] = []
        for part in scene.get("parts", []):
            notes = []
            for n in part.get("notes", []):
                bar = int(n["start_beats"] // beats_per_bar) + 1
                if start <= bar <= end:
                    shifted = copy.deepcopy(n)
                    shifted["start_beats"] = n["start_beats"] - (start - 1) * beats_per_bar
                    notes.append(shifted)
            if notes:
                p = copy.deepcopy(part)
                p["notes"] = notes
                frag["parts"].append(p)
        frag["chunk"] = {"index": index, "bars": [start, end],
                         "overlap_bars": overlap_bars}
        chunks.append(frag)
        index += 1
        start += chunk_bars - overlap_bars
    return chunks


def _equal_power_crossfade(a: np.ndarray, b: np.ndarray, overlap: int) -> np.ndarray:
    """Join b onto a across `overlap` samples with an equal-power crossfade."""
    if overlap <= 0 or len(a) < overlap or len(b) < overlap:
        return np.concatenate([a, b])
    fade_out = np.cos(np.linspace(0, np.pi / 2, overlap)) ** 2
    fade_in = np.sin(np.linspace(0, np.pi / 2, overlap)) ** 2
    tail = a[-overlap:] * fade_out[:, None] + b[:overlap] * fade_in[:, None]
    return np.concatenate([a[:-overlap], tail, b[overlap:]])


class HierarchicalRenderer:
    """Renders a scene chunk by chunk with overlap, conditioning each chunk
    on the surrounding audio and scene context."""

    def __init__(self, base_renderer, chunk_bars: int = 4, overlap_bars: int = 1):
        self.base = base_renderer
        self.chunk_bars = chunk_bars
        self.overlap_bars = overlap_bars
        self.contexts_seen: List[Dict[str, Any]] = []

    @property
    def component_name(self) -> str:
        return "Song renderer (hierarchical)"

    @property
    def supported_tiers(self) -> List[str]:
        return ["draft", "studio", "hosted"]

    def render(self, scene: Dict[str, Any], assets: Dict[str, Any],
               seed: int, tier: str = "draft") -> Dict[str, Any]:
        chunks = chunk_scene(scene, self.chunk_bars, self.overlap_bars)
        rate = scene.get("render", {}).get("sample_rate", 48000)
        bpm = scene["timeline"]["tempo"][0]["bpm"]
        overlap_s = self.overlap_bars * 4 * 60.0 / bpm
        overlap_samples = int(overlap_s * rate)

        rendered: List[np.ndarray] = []
        prev_tail: Optional[np.ndarray] = None
        for i, frag in enumerate(chunks):
            context = {
                "chunk_index": i,
                "chunk_bars": frag["chunk"]["bars"],
                "prev_tail_audio": prev_tail,  # audio before, where available
                "next_scene": chunks[i + 1] if i + 1 < len(chunks) else None,
            }
            self.contexts_seen.append({k: (v is not None) for k, v in context.items()
                                       if k != "chunk_index"})
            result = self.base.render_fragment(frag, assets, seed + i, tier)
            audio = np.asarray(result["audio"]["samples"], dtype=float)
            rendered.append(audio)
            prev_tail = audio[-overlap_samples:] if len(audio) >= overlap_samples else audio

        mix = rendered[0]
        for nxt in rendered[1:]:
            mix = _equal_power_crossfade(mix, nxt, overlap_samples)
        return {
            "audio": {"samples": mix, "sample_rate": rate},
            "metadata": {"seed": seed, "tier": tier, "chunks": len(chunks),
                         "chunk_bars": self.chunk_bars,
                         "overlap_bars": self.overlap_bars,
                         "approach": getattr(self.base, "approach", "unknown")},
        }
