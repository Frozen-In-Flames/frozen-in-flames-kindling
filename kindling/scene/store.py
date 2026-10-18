"""Scene store (Part 3.5).

Immutable versions, branches, element-level diffs, merges with conflict
reporting, and content-addressed references to assets. Version ids are the
sha256 of the canonical scene JSON, so identical scenes always get identical
ids and any change is visible.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from kindling.interfaces import SceneStore as SceneStoreABC
from kindling.scene.model import clone_scene, validate_scene


def asset_ref(asset_id: str, version: str, sha256: Optional[str] = None) -> Dict[str, Any]:
    """Content-addressed reference to an asset. Display form is id@version."""
    ref: Dict[str, Any] = {"id": asset_id, "version": version}
    if sha256:
        ref["sha256"] = sha256
    return ref


def format_asset_ref(ref: Dict[str, Any]) -> str:
    return f"{ref['id']}@{ref['version']}"


def parse_asset_ref(text: str) -> Dict[str, Any]:
    asset_id, _, version = text.partition("@")
    if not asset_id or not version:
        raise ValueError(f"not an asset reference: {text!r}")
    return {"id": asset_id, "version": version}


def _canonical(scene: Dict[str, Any]) -> str:
    return json.dumps(scene, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hashable(scene: Dict[str, Any]) -> Dict[str, Any]:
    """The content the version id covers. The volatile creation timestamp is
    object metadata, not musical content, so it is excluded: two scenes with
    identical musical content get identical ids."""
    hashed = {k: v for k, v in scene.items() if k != "id"}
    provenance = dict(hashed.get("provenance", {}))
    provenance.pop("created_at", None)
    hashed["provenance"] = provenance
    return hashed


def version_id_for(scene: Dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical(_hashable(scene)).encode("utf-8")).hexdigest()
    return "scn_" + digest[:16]


def _index(elements: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {e["id"]: e for e in elements if isinstance(e, dict) and "id" in e}


def _fmt_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3g}"
    return json.dumps(value, sort_keys=True)


def _section_label(section: Dict[str, Any]) -> str:
    ordinal = ""
    return f"{section.get('type', '?')} ({section['id']})"


def diff_scenes(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    """Human-readable element-level diff, Part 3.5.

    Example: ["chorus (sec_chorus2): energy 0.6 -> 0.8", "added part 'pad' (role: pad)"].
    """
    lines: List[str] = []

    def diff_indexed(key: str, label: str, fields: List[str]) -> None:
        old_idx, new_idx = _index(old.get(key, [])), _index(new.get(key, []))
        for eid in sorted(set(old_idx) | set(new_idx)):
            o, n = old_idx.get(eid), new_idx.get(eid)
            if o is None:
                extra = ""
                if key == "parts":
                    extra = f" (role: {n.get('role', '?')})"
                lines.append(f"added {label} {eid!r}{extra}")
            elif n is None:
                lines.append(f"removed {label} {eid!r}")
            else:
                for f in fields:
                    ov, nv = o.get(f), n.get(f)
                    if ov != nv:
                        if key == "sections":
                            lines.append(
                                f"{_section_label(n)}: {f} {_fmt_value(ov)} -> {_fmt_value(nv)}"
                            )
                        else:
                            lines.append(f"{label} {eid!r}: {f} {_fmt_value(ov)} -> {_fmt_value(nv)}")

    diff_indexed("sections", "section", ["type", "bars", "energy", "density", "description"])
    diff_indexed("parts", "part", ["role", "instrument", "notes"])
    diff_indexed("vocals", "vocal", ["voice", "performance", "lines"])
    diff_indexed("automation", "automation lane", ["parameter", "points"])

    old_harm, new_harm = old.get("harmony", []), new.get("harmony", [])
    if old_harm != new_harm:
        lines.append("harmony: progression changed")

    old_lines = _index(old.get("lyrics", {}).get("lines", []))
    new_lines = _index(new.get("lyrics", {}).get("lines", []))
    for lid in sorted(set(old_lines) | set(new_lines)):
        o, n = old_lines.get(lid), new_lines.get(lid)
        if o is None:
            lines.append(f"added lyric line {lid!r}")
        elif n is None:
            lines.append(f"removed lyric line {lid!r}")
        elif o.get("text") != n.get("text"):
            lines.append(f"lyric line {lid!r}: text changed")

    old_preset = (old.get("production") or {}).get("preset")
    new_preset = (new.get("production") or {}).get("preset")
    if old_preset != new_preset:
        lines.append(
            f"production: preset {_fmt_value(old_preset)} -> {_fmt_value(new_preset)}"
        )

    old_render, new_render = old.get("render", {}), new.get("render", {})
    for f in ("sample_rate", "seed", "tier"):
        if old_render.get(f) != new_render.get(f):
            lines.append(f"render: {f} {_fmt_value(old_render.get(f))} -> {_fmt_value(new_render.get(f))}")

    old_tempo = old.get("timeline", {}).get("tempo", [])
    new_tempo = new.get("timeline", {}).get("tempo", [])
    if old_tempo != new_tempo:
        lines.append("timeline: tempo map changed")

    return lines


def _changed_fields(base: Optional[Dict[str, Any]], other: Optional[Dict[str, Any]]) -> Dict[str, Tuple[Any, Any]]:
    """Fields that differ between base and other: field -> (base_value, other_value)."""
    if base is None and other is None:
        return {}
    if base is None:
        return {k: (None, v) for k, v in other.items() if k != "meta"}
    if other is None:
        return {k: (v, None) for k, v in base.items() if k != "meta"}
    changes = {}
    for key in set(base) | set(other):
        if key in ("id", "meta"):
            continue
        if base.get(key) != other.get(key):
            changes[key] = (base.get(key), other.get(key))
    return changes


def merge_scenes(base: Dict[str, Any], ours: Dict[str, Any], theirs: Dict[str, Any]) -> Dict[str, Any]:
    """Three-way merge with conflict reporting, Part 3.5.

    Returns {"scene": merged, "conflicts": [...]}. Conflicts are reported, not
    silently resolved: both values are kept in the conflict record and the
    merged scene keeps the "ours" value.
    """
    merged = clone_scene(ours)
    conflicts: List[Dict[str, Any]] = []

    for key in ("sections", "parts", "vocals", "automation"):
        base_idx = _index(base.get(key, []))
        ours_idx = _index(ours.get(key, []))
        theirs_idx = _index(theirs.get(key, []))
        merged_list: List[Dict[str, Any]] = []
        for eid in sorted(set(base_idx) | set(ours_idx) | set(theirs_idx)):
            b, o, t = base_idx.get(eid), ours_idx.get(eid), theirs_idx.get(eid)
            o_changes = _changed_fields(b, o)
            t_changes = _changed_fields(b, t)
            if o is None and t is None:
                continue
            if o is None:  # removed on ours side
                if t_changes:
                    conflicts.append({"element": eid, "collection": key,
                                      "kind": "removed-vs-changed",
                                      "ours": None, "theirs": t})
                continue
            if t is None:  # removed on theirs side
                if o_changes:
                    conflicts.append({"element": eid, "collection": key,
                                      "kind": "changed-vs-removed",
                                      "ours": o, "theirs": None})
                    merged_list.append(o)
                continue
            if b is None:  # added on one or both sides
                if o is not None and t is not None and o != t:
                    conflicts.append({"element": eid, "collection": key,
                                      "kind": "added-differently",
                                      "ours": o, "theirs": t})
                merged_list.append(o if o is not None else t)
                continue
            # present on all three sides: merge field by field
            element = copy.deepcopy(o)
            for field_name, (bv, tv) in t_changes.items():
                if field_name not in o_changes:
                    element[field_name] = tv
                elif o_changes[field_name][1] != tv:
                    conflicts.append({"element": eid, "collection": key,
                                      "kind": "field",
                                      "field": field_name,
                                      "ours": o_changes[field_name][1],
                                      "theirs": tv})
            merged_list.append(element)
        merged[key] = merged_list

    return {"scene": merged, "conflicts": conflicts}


class SceneStore(SceneStoreABC):
    """In-memory scene store. Versions are immutable: load returns a deep
    copy, and saving never mutates what is already stored."""

    def __init__(self) -> None:
        self._versions: Dict[str, str] = {}
        self._branches: Dict[str, str] = {}

    @property
    def component_name(self) -> str:
        return "Scene store"

    @property
    def supported_tiers(self) -> List[str]:
        return ["draft", "studio", "hosted"]

    def save_version(self, scene: Dict[str, Any], parent_id: Optional[str] = None) -> str:
        scene = clone_scene(scene)
        validate_scene(scene)
        if parent_id is not None:
            if parent_id not in self._versions:
                raise KeyError(f"unknown parent version {parent_id}")
            scene["parent"] = parent_id
        vid = version_id_for(scene)
        scene["id"] = vid
        self._versions[vid] = _canonical(scene)
        return vid

    def load_version(self, version_id: str) -> Dict[str, Any]:
        try:
            return json.loads(self._versions[version_id])
        except KeyError:
            raise KeyError(f"unknown scene version {version_id}")

    def branch(self, version_id: str, name: str) -> str:
        if version_id not in self._versions:
            raise KeyError(f"unknown scene version {version_id}")
        self._branches[name] = version_id
        return version_id

    def branch_head(self, name: str) -> str:
        return self._branches[name]

    def merge(self, ours_id: str, theirs_id: str) -> Dict[str, Any]:
        ours = self.load_version(ours_id)
        theirs = self.load_version(theirs_id)
        base_id = self._common_ancestor(ours_id, theirs_id)
        base = self.load_version(base_id) if base_id else make_empty_base(ours)
        result = merge_scenes(base, ours, theirs)
        merged_id = self.save_version(result["scene"], parent_id=ours_id)
        return {"merged_id": merged_id, "conflicts": result["conflicts"]}

    def diff_versions(self, old_id: str, new_id: str) -> List[str]:
        return diff_scenes(self.load_version(old_id), self.load_version(new_id))

    def history(self, version_id: str) -> List[str]:
        chain = []
        current: Optional[str] = version_id
        while current is not None:
            chain.append(current)
            scene = self.load_version(current)
            current = scene.get("parent")
        return chain

    def _common_ancestor(self, a_id: str, b_id: str) -> Optional[str]:
        ancestors = set(self.history(a_id))
        for vid in self.history(b_id):
            if vid in ancestors:
                return vid
        return None


def make_empty_base(scene: Dict[str, Any]) -> Dict[str, Any]:
    from kindling.scene.model import make_scene
    base = make_scene()
    base["timeline"] = copy.deepcopy(scene.get("timeline", base["timeline"]))
    return base
