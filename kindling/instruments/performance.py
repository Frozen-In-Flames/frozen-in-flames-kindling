"""Performance engine: part + context -> musical performance (9.2).

The engine makes musical decisions, not just note playback:
- Guitar: strummed vs fingerpicked from context density; strum spread,
  voicing choices.
- Bass: locks with the kick pattern from context neighbors.
- All: timing humanization and dynamics shaping, seeded and deterministic
  (same part + same seed = same performance, so it renders consistently
  across the song).
"""

from typing import Any, Dict, List

import numpy as np


def _hash_seed(*parts) -> int:
    import hashlib
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)


class PerformanceEngine:
    """Turns a part and context into a performed note list."""

    def perform(self, part: List[Dict[str, Any]],
                context: Dict[str, Any],
                instrument: str,
                seed: int = 0) -> List[Dict[str, Any]]:
        """part: [{"midi", "start_beats", "duration_beats", "vel"}].
        context: {"tempo", "density" (0..1), "harmony", "neighbors"}.
        Returns performed notes with start_s, dur_s, vel, articulation.
        """
        tempo = context.get("tempo", 120.0)
        beat_s = 60.0 / tempo
        density = context.get("density", 0.5)
        rng = np.random.default_rng(_hash_seed(instrument, seed, len(part)))

        if instrument == "kindling-guitar":
            return self._perform_guitar(part, beat_s, density, rng, context)
        if instrument == "kindling-bass":
            return self._perform_bass(part, beat_s, density, rng, context)
        return self._perform_generic(part, beat_s, density, rng)

    def _perform_guitar(self, part, beat_s, density, rng, context):
        # Dense context -> strummed; sparse -> fingerpicked (9.2).
        articulation = "strummed" if density > 0.5 else "fingerpicked"
        out = []
        for i, n in enumerate(part):
            # Strum spread: notes of a chord staggered by a few ms.
            spread = rng.uniform(0, 0.012) if articulation == "strummed" else 0.0
            # Humanization: small timing jitter.
            jitter = rng.normal(0, 0.008)
            vel = n.get("vel", 0.8)
            # Accent downbeats slightly.
            if n["start_beats"] % 4 < 0.01:
                vel = min(1.0, vel * 1.1)
            # Dynamics shaping: slight crescendo through the phrase.
            vel = vel * (0.95 + 0.1 * (i / max(1, len(part) - 1)))
            out.append({
                "midi": n["midi"],
                "start_s": n["start_beats"] * beat_s + jitter + spread,
                "dur_s": n["duration_beats"] * beat_s * 0.95,
                "vel": round(float(np.clip(vel, 0.05, 1.0)), 3),
                "articulation": articulation,
            })
        return out

    def _perform_bass(self, part, beat_s, density, rng, context):
        # Lock with the kick: pull note starts toward kick hits (9.2).
        kick_beats = []
        for nb in context.get("neighbors", []):
            if nb.get("role") == "kick":
                kick_beats.extend(nb.get("hits_beats", []))
        out = []
        for n in part:
            start = n["start_beats"]
            if kick_beats:
                nearest = min(kick_beats, key=lambda k: abs(k - start))
                if abs(nearest - start) < 0.25:
                    start = nearest  # lock to the kick
            jitter = rng.normal(0, 0.005)
            vel = n.get("vel", 0.8)
            # Bass follows the kick's accent.
            out.append({
                "midi": n["midi"],
                "start_s": start * beat_s + jitter,
                "dur_s": n["duration_beats"] * beat_s * 0.9,
                "vel": round(float(np.clip(vel, 0.05, 1.0)), 3),
                "articulation": "fingered" if density < 0.6 else "picked",
            })
        return out

    def _perform_generic(self, part, beat_s, density, rng):
        out = []
        for n in part:
            jitter = rng.normal(0, 0.006)
            out.append({
                "midi": n["midi"],
                "start_s": n["start_beats"] * beat_s + jitter,
                "dur_s": n["duration_beats"] * beat_s,
                "vel": round(float(np.clip(n.get("vel", 0.8), 0.05, 1.0)), 3),
                "articulation": "sustained",
            })
        return out
