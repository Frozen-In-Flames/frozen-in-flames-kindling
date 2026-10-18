"""Asset library (Phase A): on-disk, versioned, content-addressed.

Layout under the library root:
  assets/<asset_id>.json   the asset record (metadata + kind payload)
  audio/<sha256>.wav       source audio, content-addressed, mono 44100
  index.json               id -> {asset_kind, name, version, updated_at}

An asset record:
  {kind: "kindling/asset-record", schema_version, id, asset_kind
   (voice|instrument|preset|profile), name, version, owner, created_at,
   source_audio_sha256 (or null), provenance, consent (voice only),
   notes (list), payload (the kind-specific asset dict)}

Delete cascades: removing an asset removes its record and its source audio
when no other asset references that audio (Part 19.4, library scope).
Profile-trait cascade hooks are documented for Phase B.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audio import audio_sha256, load_audio

RECORD_KIND = "kindling/asset-record"
RECORD_SCHEMA_VERSION = "1.0"
ASSET_KINDS = ("voice", "instrument", "preset", "profile")

_ID_PREFIX = {"voice": "voice_", "instrument": "inst_",
              "preset": "preset_", "profile": "prof_"}


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "asset"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_library_root() -> str:
    return os.path.join(os.path.expanduser("~"), ".kindling", "library")


class AssetLibrary:
    """On-disk asset library."""

    def __init__(self, root: str = None):
        self.root = Path(root or default_library_root())
        self.assets_dir = self.root / "assets"
        self.audio_dir = self.root / "audio"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    # -- records ------------------------------------------------------
    def _record_path(self, asset_id: str) -> Path:
        return self.assets_dir / f"{asset_id}.json"

    def _write_record(self, record: Dict[str, Any]) -> None:
        tmp = self._record_path(record["id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=1, default=str))
        tmp.replace(self._record_path(record["id"]))
        self._write_index()

    def _write_index(self) -> None:
        index = {}
        for path in sorted(self.assets_dir.glob("*.json")):
            try:
                rec = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            index[rec["id"]] = {
                "asset_kind": rec.get("asset_kind"),
                "name": rec.get("name"),
                "version": rec.get("version"),
                "updated_at": rec.get("updated_at", rec.get("created_at")),
            }
        (self.root / "index.json").write_text(json.dumps(index, indent=1))

    def _unique_id(self, asset_kind: str, name: str) -> str:
        base = _ID_PREFIX[asset_kind] + _slug(name)
        candidate, n = base, 2
        while self._record_path(candidate).exists():
            candidate = f"{base}_{n}"
            n += 1
        return candidate

    def store_audio(self, samples, rate: int) -> str:
        """Store mono 44100 audio content-addressed. Returns the sha."""
        import numpy as np
        mono = np.asarray(samples, dtype=np.float32).reshape(-1)
        sha = audio_sha256(mono, rate)
        path = self.audio_dir / f"{sha}.wav"
        if not path.exists():
            from kindling.mix.export import write_wav
            write_wav(str(path), np.stack([mono, mono]), rate, 16)
        return sha

    def audio_path(self, sha: str) -> str:
        path = self.audio_dir / f"{sha}.wav"
        if not path.exists():
            raise KeyError(f"audio {sha} not in library")
        return str(path)

    def load_audio_mono(self, sha: str):
        samples, rate = load_audio(self.audio_path(sha), target_rate=44100,
                                   mono=True)
        return samples, rate

    # -- CRUD ----------------------------------------------------------
    def save_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        record = copy.deepcopy(record)
        record["kind"] = RECORD_KIND
        record["schema_version"] = RECORD_SCHEMA_VERSION
        record.setdefault("version", "v1")
        record["updated_at"] = _now()
        record.setdefault("created_at", record["updated_at"])
        self._write_record(record)
        return copy.deepcopy(record)

    def get(self, asset_id: str) -> Dict[str, Any]:
        path = self._record_path(asset_id)
        if not path.exists():
            raise KeyError(f"unknown asset {asset_id!r}")
        return json.loads(path.read_text())

    def list(self, asset_kind: str = None) -> List[Dict[str, Any]]:
        out = []
        for path in sorted(self.assets_dir.glob("*.json")):
            rec = json.loads(path.read_text())
            if asset_kind and rec.get("asset_kind") != asset_kind:
                continue
            out.append({"id": rec["id"], "asset_kind": rec.get("asset_kind"),
                        "name": rec.get("name"), "version": rec.get("version"),
                        "owner": (rec.get("owner") or {}).get("id"),
                        "created_at": rec.get("created_at")})
        return out

    def rename(self, asset_id: str, new_name: str) -> Dict[str, Any]:
        rec = self.get(asset_id)
        rec["name"] = new_name
        if rec["asset_kind"] == "voice" and isinstance(rec.get("payload"), dict):
            rec["payload"]["name"] = new_name
        return self.save_record(rec)

    def delete(self, asset_id: str) -> Dict[str, Any]:
        """Delete an asset. Cascades to its source audio when no other asset
        references it. Returns a report of what was removed."""
        rec = self.get(asset_id)
        removed = [f"assets/{asset_id}.json"]
        self._record_path(asset_id).unlink()
        sha = rec.get("source_audio_sha256")
        audio_removed = False
        if sha:
            still_used = any(
                r.get("source_audio_sha256") == sha
                for r in (self.get(a["id"]) for a in self.list()))
            if not still_used:
                p = self.audio_dir / f"{sha}.wav"
                if p.exists():
                    p.unlink()
                    audio_removed = True
                    removed.append(f"audio/{sha}.wav")
        self._write_index()
        return {"deleted": asset_id, "removed": removed,
                "audio_removed": audio_removed,
                "note": "profile-trait cascade is a Phase B hook; no profile "
                        "store is wired to the library in Phase A"}

    # -- ingest ---------------------------------------------------------
    def ingest(self, record: Dict[str, Any],
               audio_path: str = None,
               notes: List[str] = None) -> Dict[str, Any]:
        """Import a prebuilt asset. Accepts either a library asset record
        (kind kindling/asset-record) or a raw kind payload: a voice
        character (kind kindling/voice-character) is wrapped into a voice
        record automatically."""
        record = copy.deepcopy(record)
        if record.get("kind") == "kindling/voice-character":
            char = record
            record = {
                "id": char.get("id", "voice_" + _slug(char.get("name", "voice"))),
                "asset_kind": "voice",
                "name": char.get("name", "unnamed"),
                "version": char.get("version", "v1"),
                "owner": char.get("owner", {"id": "unknown"}),
                "consent": char.get("consent"),
                "provenance": char.get("provenance", {}),
                "payload": char,
            }
        for field in ("id", "asset_kind", "name", "payload"):
            if field not in record:
                raise ValueError(f"ingest record missing {field!r}")
        if record["asset_kind"] not in ASSET_KINDS:
            raise ValueError(f"unknown asset_kind {record['asset_kind']!r}")
        if self._record_path(record["id"]).exists():
            raise ValueError(f"asset {record['id']!r} already in library; "
                             "delete it first or rename")
        rec = copy.deepcopy(record)
        if notes:
            rec.setdefault("notes", []).extend(notes)
        if audio_path:
            samples, rate = load_audio(audio_path, target_rate=44100, mono=True)
            rec["source_audio_sha256"] = self.store_audio(samples, rate)
            rec.setdefault("provenance", {})["source_audio_file"] = \
                os.path.basename(audio_path)
        return self.save_record(rec)


class LibraryVoiceStore:
    """Adapter: presents library voice records through the voice-character
    store interface used by render_with_character (get/list/revoke)."""

    def __init__(self, library: AssetLibrary):
        self.library = library

    def get(self, voice_id: str, version: str = None) -> Dict[str, Any]:
        rec = self.library.get(voice_id)
        if rec.get("asset_kind") != "voice":
            raise KeyError(f"{voice_id!r} is not a voice asset")
        voice = copy.deepcopy(rec["payload"])
        if version is not None and voice.get("version") != version:
            raise KeyError(f"voice {voice_id!r} has no version {version!r}")
        return voice

    def list(self) -> List[Dict[str, Any]]:
        return [self.get(r["id"]) for r in self.library.list("voice")]

    def revoke(self, voice_id: str) -> None:
        rec = self.library.get(voice_id)
        rec["payload"]["revoked"] = True
        self.library.save_record(rec)

    def sufficiency_report(self, voice_id: str,
                           performance: Dict[str, Any]) -> Dict[str, Any]:
        from kindling.assets.voice import check_performance_supported
        return check_performance_supported(self.get(voice_id), performance)
