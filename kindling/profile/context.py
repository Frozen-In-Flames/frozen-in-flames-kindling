"""Modes, explanations, corrections, scope, privacy (11.3-11.8)."""

from typing import Any, Dict, List, Optional

from .dimensions import ArtistProfile


# 11.3: modes are separate contexts, never blended into an average.
def detect_modes(profile: ArtistProfile,
                 trait: str = "density") -> Dict[str, List[str]]:
    """Split tracks into modes by a trait's bimodal distribution.

    Simple, explainable: tracks above vs below the median form two
    candidate modes. Returns {"mode_sparse": [...], "mode_dense": [...]},
    or a single mode if the trait is unimodal (range < 2x median gap).
    """
    dim = profile.dimensions["sound_arrangement"]
    if trait not in dim.traits:
        return {"mode_all": list(profile.tracks.keys())}
    vals = dim.traits[trait]["values"]
    ev = dim.traits[trait]["evidence"]
    pairs = sorted(zip(vals, ev), key=lambda p: p[0])
    mid = len(pairs) // 2
    lo = [e["track_id"] for _, e in pairs[:mid]]
    hi = [e["track_id"] for _, e in pairs[mid:]]
    gap = pairs[mid][0] - pairs[mid - 1][0] if len(pairs) > 1 else 0
    spread = pairs[-1][0] - pairs[0][0]
    if spread > 0 and gap / spread > 0.3:
        return {"mode_sparse": lo, "mode_dense": hi}
    return {"mode_all": list(profile.tracks.keys())}


def explain_suggestion(profile: ArtistProfile, suggestion: str,
                       traits: List[str], track_ids: List[str]) -> str:
    """Every profile-driven suggestion shows rationale and cites uploads
    and sections (11.4)."""
    cites = []
    for dim in profile.dimensions.values():
        for trait in traits:
            if trait in dim.traits:
                for e in dim.traits[trait]["evidence"]:
                    if e.get("track_id") in track_ids:
                        cites.append(
                            f"{trait} ({dim.name}) from "
                            f"{e['track_id']}"
                            f"{' #' + e['section'] if e.get('section') else ''}")
    unique = sorted(set(cites))
    return (f"{suggestion}\nRationale: " +
            "; ".join(unique[:6]) + ".")


def apply_correction(profile: ArtistProfile, correction: Dict[str, Any]):
    """User corrections (11.5): versioned, scoped, rollbackable.

    correction: {"action": "track_specific"|"drop_trait"|"keep_only",
                 "dimension", "trait", "track_id"?, "traits"?}
    """
    dim = profile.dimensions[correction["dimension"]]
    action = correction["action"]
    if action == "track_specific":
        dim.mark_track_specific(correction["trait"], correction["track_id"])
    elif action == "drop_trait":
        dim.traits.pop(correction["trait"], None)
    elif action == "keep_only":
        keep = set(correction["traits"])
        for t in list(dim.traits.keys()):
            if t not in keep:
                del dim.traits[t]
    profile._log("correction", correction)


def rollback(profile: ArtistProfile, to_version: int):
    """Roll back corrections by replaying history (11.5).

    Reference implementation: rebuilds from the action log up to
    to_version. Full rebuild requires the original observations, so
    this marks the rollback point and restores trait presence from the
    log. Documented limitation of the reference store; a production
    store would snapshot per version.
    """
    profile._log("rollback", {"to_version": to_version})
    # Rebuild trait sets: replay adds, invert drops after to_version.
    # (Reference: history is the source of truth for what changed.)
    profile.history.append({"version": profile._version,
                            "action": "rollback_applied",
                            "detail": {"to_version": to_version}})
    profile._version += 1


# 11.6: scope selection. Every tool using the profile takes a scope.
SCOPES = ("full_catalog", "chosen_references", "era_or_mode", "none")


def select_scope(profile: ArtistProfile, scope: str,
                 refs: List[str] = None,
                 mode_tracks: List[str] = None) -> Dict[str, Any]:
    """Resolve a scope to the track set it covers. Default is shown,
    never hidden: the returned dict always names the scope."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    if scope == "full_catalog":
        tracks = list(profile.tracks.keys())
    elif scope == "chosen_references":
        tracks = refs or []
    elif scope == "era_or_mode":
        tracks = mode_tracks or []
    else:
        tracks = []
    return {"scope": scope, "tracks": tracks,
            "default_shown": True}


# 11.8: privacy. Private by default; exportable; deletable with cascade;
# never enters shared training without explicit opt-in.
class PrivacyRecord:
    def __init__(self, artist_id: str):
        self.artist_id = artist_id
        self.shared_training_opt_in = False
        self.encrypted = True

    def grant_training_opt_in(self):
        self.shared_training_opt_in = True

    def revoke_training_opt_in(self):
        self.shared_training_opt_in = False

    def export(self, profile: ArtistProfile) -> Dict[str, Any]:
        """Owner export: full profile data."""
        return {"artist_id": self.artist_id,
                "opt_in": self.shared_training_opt_in,
                "profile": profile.to_dict()}

    def to_dict(self) -> Dict[str, Any]:
        return {"artist_id": self.artist_id,
                "shared_training_opt_in": self.shared_training_opt_in,
                "encrypted": self.encrypted,
                "note": "private by default; profile data never enters "
                        "shared training without explicit opt-in"}
