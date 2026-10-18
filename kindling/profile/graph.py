"""Relationship graph (11.2): tracks, sections, parts, traits.

Every edge points to audible evidence (a section, pattern, role, or
feature), not only a similarity score. Answers: what do two tracks
share; what makes one an outlier; which traits recur in choruses but
not verses.
"""

from typing import Any, Dict, List, Set


class ProfileGraph:
    """Nodes are tracks/sections/traits; edges carry evidence."""

    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []

    def add_track(self, track_id: str, sections: List[str]):
        self.nodes[track_id] = {"kind": "track", "sections": sections}
        for sec in sections:
            sid = f"{track_id}#{sec}"
            self.nodes[sid] = {"kind": "section", "track": track_id,
                               "name": sec}
            self.edges.append({"from": track_id, "to": sid,
                               "kind": "has_section",
                               "evidence": {"section": sec}})

    def add_trait(self, trait_id: str, dimension: str, section_id: str,
                  evidence: Dict[str, Any]):
        """Link a trait observation to the section where it is audible."""
        if trait_id not in self.nodes:
            self.nodes[trait_id] = {"kind": "trait", "dimension": dimension}
        self.edges.append({"from": section_id, "to": trait_id,
                           "kind": "exhibits",
                           "evidence": {"section": section_id,
                                        **evidence}})

    def shared_traits(self, track_a: str, track_b: str) -> List[Dict]:
        """What do these two tracks share, with evidence."""
        traits_a = self._track_traits(track_a)
        traits_b = self._track_traits(track_b)
        shared = []
        for t in traits_a & traits_b:
            ev_a = self._evidence_for(track_a, t)
            ev_b = self._evidence_for(track_b, t)
            shared.append({"trait": t, "evidence_a": ev_a,
                           "evidence_b": ev_b})
        return shared

    def outlier_traits(self, track_id: str,
                       others: List[str]) -> List[Dict]:
        """Traits this track has that the others do not, with evidence."""
        mine = self._track_traits(track_id)
        theirs: Set[str] = set()
        for o in others:
            theirs |= self._track_traits(o)
        return [{"trait": t, "evidence": self._evidence_for(track_id, t)}
                for t in mine - theirs]

    def chorus_not_verse_traits(self) -> List[str]:
        """Traits recurring in choruses but not verses (11.2)."""
        chorus_traits: Set[str] = set()
        verse_traits: Set[str] = set()
        for e in self.edges:
            if e["kind"] != "exhibits":
                continue
            sec = self.nodes.get(e["from"], {})
            name = sec.get("name", "")
            if "chorus" in name:
                chorus_traits.add(e["to"])
            elif "verse" in name:
                verse_traits.add(e["to"])
        return sorted(chorus_traits - verse_traits)

    def _track_traits(self, track_id: str) -> Set[str]:
        traits = set()
        for e in self.edges:
            if e["kind"] != "exhibits":
                continue
            sec = self.nodes.get(e["from"], {})
            if sec.get("track") == track_id:
                traits.add(e["to"])
        return traits

    def _evidence_for(self, track_id: str, trait_id: str) -> List[Dict]:
        out = []
        for e in self.edges:
            if e["kind"] != "exhibits" or e["to"] != trait_id:
                continue
            sec = self.nodes.get(e["from"], {})
            if sec.get("track") == track_id:
                out.append(e["evidence"])
        return out
