"""Takes (12.5): generate alternatives, compare, comp across takes.

Every take is a version. Comping picks the best regions across takes.
"""

from typing import Any, Dict, List

import numpy as np


class TakeManager:
    """Generate and manage takes of an edit."""

    def __init__(self):
        self.takes: Dict[str, Dict[str, Any]] = {}

    def add_take(self, take_id: str, audio: np.ndarray, rate: int,
                 seed: int, metadata: Dict[str, Any] = None):
        self.takes[take_id] = {"audio": np.asarray(audio), "rate": rate,
                               "seed": seed,
                               "metadata": metadata or {}}

    def list_takes(self) -> List[str]:
        return sorted(self.takes.keys())

    def comp(self, regions: List[Dict[str, Any]]) -> np.ndarray:
        """Comp across takes: regions = [{"take_id", "start_s", "end_s"}].

        Crossfades at region boundaries.
        """
        if not regions:
            raise ValueError("no regions to comp")
        rate = self.takes[regions[0]["take_id"]]["rate"]
        total_s = max(r["end_s"] for r in regions)
        out = np.zeros(int(total_s * rate))
        for r in regions:
            take = self.takes[r["take_id"]]
            assert take["rate"] == rate, "take rate mismatch"
            s0, s1 = int(r["start_s"] * rate), int(r["end_s"] * rate)
            seg = take["audio"][s0:s1]
            # 10 ms crossfade with previous.
            f = int(rate * 0.01)
            if s0 > 0 and f < len(seg):
                fade = np.linspace(0, 1, f)
                seg = seg.copy()
                seg[:f] = seg[:f] * fade + out[s0:s0 + f] * (1 - fade)
            out[s0:s0 + len(seg)] = seg
        return out

    def best_take(self, metric) -> str:
        """Pick the take maximizing metric(take_dict)."""
        return max(self.takes.keys(), key=lambda k: metric(self.takes[k]))
