"""Artist profile dimensions (11.1).

Five separate, inspectable dimensions. Each stores tendencies and ranges,
not a recipe. NEVER collapsed into a single style vector.
"""

from typing import Any, Dict, List


DIMENSIONS = (
    "musical_identity",  # harmony, melody shapes, rhythmic feel, phrasing, structure
    "sound_arrangement",  # instruments, roles, combinations, density, register
    "performance",  # vocal character, delivery, timing, dynamics, articulation
    "production",  # tonal balance, space, effects, stereo, dynamics, automation
    "variation",  # what changes by track, section, era, mood
)


class Dimension:
    """One profile dimension: traits with observed ranges and evidence."""

    def __init__(self, name: str):
        if name not in DIMENSIONS:
            raise ValueError(f"unknown dimension {name!r}")
        self.name = name
        self.traits: Dict[str, Dict[str, Any]] = {}

    def observe(self, trait: str, value: Any, evidence: Dict[str, str],
                track_id: str):
        """Record one observation of a trait with audible evidence."""
        if trait not in self.traits:
            self.traits[trait] = {"values": [], "evidence": [],
                                  "track_specific": {}}
        self.traits[trait]["values"].append(value)
        self.traits[trait]["evidence"].append({**evidence,
                                               "track_id": track_id})

    def tendency(self, trait: str) -> Dict[str, Any]:
        """Tendency and range for a trait (numeric: mean/min/max)."""
        t = self.traits[trait]
        vals = t["values"]
        if all(isinstance(v, (int, float)) for v in vals):
            return {"mean": round(sum(vals) / len(vals), 3),
                    "min": round(min(vals), 3),
                    "max": round(max(vals), 3),
                    "observations": len(vals)}
        # Categorical: most common value and its share.
        counts: Dict[Any, int] = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        top = max(counts, key=counts.get)
        return {"mode": top, "share": round(counts[top] / len(vals), 2),
                "observations": len(vals)}

    def mark_track_specific(self, trait: str, track_id: str):
        """Correction (11.5): this trait belongs to one track only."""
        self.traits[trait]["track_specific"][track_id] = True

    def is_track_specific(self, trait: str, track_id: str) -> bool:
        return self.traits[trait].get("track_specific", {}).get(track_id,
                                                                False)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "traits": self.traits}


class ArtistProfile:
    """The full profile: five dimensions, never one vector (11.1)."""

    def __init__(self, artist_id: str):
        self.artist_id = artist_id
        self.dimensions = {d: Dimension(d) for d in DIMENSIONS}
        self.tracks: Dict[str, Dict[str, Any]] = {}
        self.history: List[Dict[str, Any]] = []
        self._version = 1

    @property
    def version(self) -> int:
        return self._version

    def add_track(self, track_id: str, analysis: Dict[str, Any]):
        """Add a track-level analysis. analysis maps dimension -> trait ->
        (value, evidence)."""
        self.tracks[track_id] = analysis
        for dim_name, traits in analysis.items():
            if dim_name not in self.dimensions:
                continue
            dim = self.dimensions[dim_name]
            for trait, (value, evidence) in traits.items():
                dim.observe(trait, value, evidence, track_id)
        self._log("add_track", {"track_id": track_id})

    def remove_track(self, track_id: str):
        """Delete a track AND its derived traits (11.8, acceptance)."""
        if track_id not in self.tracks:
            return
        del self.tracks[track_id]
        for dim in self.dimensions.values():
            for trait in list(dim.traits.keys()):
                t = dim.traits[trait]
                keep_vals, keep_ev = [], []
                for v, e in zip(t["values"], t["evidence"]):
                    if e.get("track_id") != track_id:
                        keep_vals.append(v)
                        keep_ev.append(e)
                if keep_vals:
                    t["values"], t["evidence"] = keep_vals, keep_ev
                else:
                    del dim.traits[trait]
        self._log("remove_track", {"track_id": track_id})

    def _log(self, action: str, detail: Dict[str, Any]):
        self.history.append({"version": self._version, "action": action,
                             "detail": detail})
        self._version += 1

    def to_dict(self) -> Dict[str, Any]:
        return {"artist_id": self.artist_id, "version": self._version,
                "dimensions": {d: dim.to_dict()
                               for d, dim in self.dimensions.items()},
                "tracks": list(self.tracks.keys()),
                "history": self.history}
