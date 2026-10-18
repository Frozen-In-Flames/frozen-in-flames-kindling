"""The data pipeline (Part 4.1, 4.3).

Stages: ingest and validate; normalize format and apply the loudness policy;
deduplicate; segment; analyze; detect and separate vocals and instruments
while keeping the original mix; transcribe/align lyrics; label instruments
and roles; score annotation quality; assign splits; write the record.

Splits are fixed early and never leak: assignment is deterministic from the
content hash, and near-duplicates are forced into the same split as the
original (Part 4.3).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from kindling.data import analysis as analysis_mod
from kindling.data.record import label, make_record, validate_record
from kindling.interfaces import DataPipeline as DataPipelineABC
from kindling.scene.audio_import import read_wav_mono

PROCESSING_VERSIONS = {
    "pipeline": "4.0.0",
    "analysis": "4.0.0",
    "record_schema": "4.0.0",
}

CANONICAL_RATE = 48000
NEAR_DUPE_MAX_HAMMING = 51  # ~10% of 512 bits


def sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def fingerprint(samples: np.ndarray, rate: int) -> bytes:
    """512-bit perceptual fingerprint: 64 windows, 4 bits of normalized RMS
    and 4 bits of zero-crossing rate each. Robust to small gain changes."""
    windows = np.array_split(samples, 64)
    rms = np.array([float(np.sqrt(np.mean(w ** 2))) for w in windows])
    zcrs = np.array([float(((w[:-1] * w[1:]) < 0).mean()) if len(w) > 1 else 0.0
                     for w in windows])
    rms_peak = rms.max() or 1.0
    out = bytearray()
    for r, z in zip(rms, zcrs):
        out.append(((int(r / rms_peak * 15) & 0xF) << 4) | (int(z * 15) & 0xF))
    return bytes(out)


def hamming_distance(a: bytes, b: bytes) -> int:
    return sum(bin(x ^ y).count("1") for x, y in zip(a, b))


def resample_linear(samples: np.ndarray, rate: int, target_rate: int) -> np.ndarray:
    if rate == target_rate:
        return samples
    duration = len(samples) / rate
    target_len = int(round(duration * target_rate))
    positions = np.linspace(0, len(samples) - 1, target_len)
    return np.interp(positions, np.arange(len(samples)), samples).astype(np.float64)


def assign_split(content_hash: str) -> str:
    bucket = int(content_hash.split(":")[1], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "validate"
    return "test"


class Pipeline(DataPipelineABC):
    def __init__(self, ledger_dir: str):
        self.ledger_dir = ledger_dir
        os.makedirs(ledger_dir, exist_ok=True)
        self._records: Dict[str, Dict[str, Any]] = {}
        self._by_hash: Dict[str, str] = {}
        self._fingerprints: List[tuple] = []  # (record_id, fingerprint bytes, split)
        self._load_existing()

    @property
    def component_name(self) -> str:
        return "Data pipeline"

    @property
    def supported_tiers(self) -> List[str]:
        return ["hosted"]

    # -- persistence -----------------------------------------------------
    def _record_path(self, record_id: str) -> str:
        return os.path.join(self.ledger_dir, record_id + ".json")

    def _load_existing(self) -> None:
        for name in os.listdir(self.ledger_dir):
            if name.endswith(".json"):
                with open(os.path.join(self.ledger_dir, name), encoding="utf-8") as fh:
                    record = json.load(fh)
                self._records[record["record_id"]] = record
                self._by_hash[record["content_hash"]] = record["record_id"]
                if record.get("fingerprint"):
                    self._fingerprints.append(
                        (record["record_id"], bytes.fromhex(record["fingerprint"]),
                         record["split"]))

    def _persist(self, record: Dict[str, Any]) -> None:
        validate_record(record)
        with open(self._record_path(record["record_id"]), "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)

    # -- stages ----------------------------------------------------------
    def ingest(self, source: Dict[str, Any]) -> str:
        """Ingest one audio file. source: {path, name, acquisition, license,
        transcript (optional list of syllables), stereo_path optional}."""
        path = source["path"]
        audio = read_wav_mono(path)
        content_hash = sha256_of_file(path)

        if content_hash in self._by_hash:
            return self._by_hash[content_hash]  # exact duplicate: keep the first

        record_id = "rec_" + content_hash.split(":")[1][:16]
        record = make_record(record_id, content_hash, {
            "name": source.get("name", os.path.basename(path)),
            "acquisition": source.get("acquisition", "upload"),
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }, source.get("license", {"status": "unknown", "training_allowed": False}))
        record["processing_versions"] = dict(PROCESSING_VERSIONS)

        problems = self._validate_audio(audio)
        record["flags"].extend(problems)

        mono = np.asarray(audio["samples"], dtype=float)
        canonical = resample_linear(mono, audio["sample_rate"], CANONICAL_RATE)
        record["labels"]["loudness_dbfs"] = label(
            analysis_mod.approximate_loudness_dbfs(canonical), 0.7, "rms-approx")

        fp = fingerprint(canonical, CANONICAL_RATE)
        record["fingerprint"] = fp.hex()
        near = self._find_near_dupe(fp, content_hash)
        if near:
            record["flags"].append(f"near-duplicate-of:{near}")

        for name, lab in analysis_mod.analyze_track(
                list(canonical), CANONICAL_RATE).items():
            record["labels"][name] = lab

        if audio["channels"] > 1:
            record["labels"]["stem_center_estimate"] = label(
                "mid-side reference separation kept with mix", 0.4,
                "mid-side-reference")

        transcript = source.get("transcript")
        if transcript:
            record["labels"]["lyric_alignment"] = analysis_mod.align_syllables_to_vocal_onsets(
                canonical, CANONICAL_RATE, transcript)
        else:
            record["labels"]["lyric_alignment"] = label(
                None, 0.0, "no-transcript",
            )
            record["flags"].append("no-transcript-provided")

        record["quality_score"] = self._score(record)
        record["split"] = self._assign_split_no_leak(record, near)
        record["allowed_uses"] = self._allowed_uses(record)

        self._records[record_id] = record
        self._by_hash[content_hash] = record_id
        self._fingerprints.append((record_id, fp, record["split"]))
        self._persist(record)
        return record_id

    def _validate_audio(self, audio: Dict[str, Any]) -> List[str]:
        problems = []
        if audio["duration_s"] < 1.0:
            problems.append("too-short")
        samples = audio["samples"]
        peak = max((abs(s) for s in samples), default=0.0)
        if peak <= 0.0:
            problems.append("silent")
        if peak > 1.0:
            problems.append("clipped-input")
        return problems

    def _find_near_dupe(self, fp: bytes, content_hash: str) -> Optional[str]:
        for record_id, other_fp, _ in self._fingerprints:
            if self._records[record_id]["content_hash"] == content_hash:
                continue
            if hamming_distance(fp, other_fp) <= NEAR_DUPE_MAX_HAMMING:
                return record_id
        return None

    def _assign_split_no_leak(self, record: Dict[str, Any],
                              near: Optional[str]) -> str:
        if near:
            # Near-duplicates (including alternate mixes) stay with the
            # original: splits never leak (Part 4.3).
            original_split = self._records[near]["split"]
            record["flags"].append(f"split-pinned-to:{near}")
            return original_split
        return assign_split(record["content_hash"])

    def _allowed_uses(self, record: Dict[str, Any]) -> List[str]:
        lic = record["license"]
        if lic["status"] == "cleared" and lic["training_allowed"]:
            return ["train", "evaluate"]
        if lic["training_allowed"]:
            return ["evaluate"]
        return ["none"]

    def _score(self, record: Dict[str, Any]) -> float:
        confs = [lab.get("confidence", 0.0)
                 for lab in record["labels"].values()
                 if isinstance(lab, dict)]
        base = sum(confs) / len(confs) if confs else 0.0
        penalty = 0.1 * len([f for f in record["flags"]
                             if not f.startswith("near-duplicate-of")])
        return round(max(0.0, min(1.0, base - penalty)), 3)

    # -- interface -------------------------------------------------------
    def record(self, record_id: str) -> Dict[str, Any]:
        return self._records[record_id]

    def delete(self, record_id: str) -> None:
        from kindling.data.ledger import delete_record
        delete_record(self, record_id, reason="pipeline-request")

    def all_records(self) -> List[Dict[str, Any]]:
        return list(self._records.values())

    def leakage_audit(self) -> Dict[str, Any]:
        """Zero cross-split duplicates: no two records in different splits
        share a content hash or a near-duplicate fingerprint."""
        issues = []
        seen_hash: Dict[str, str] = {}
        for record in self._records.values():
            if record.get("deleted"):
                continue
            h = record["content_hash"]
            if h in seen_hash and seen_hash[h] != record["split"]:
                issues.append(f"hash {h} in splits {seen_hash[h]} and {record['split']}")
            seen_hash[h] = record["split"]
        fps = [(r["record_id"], bytes.fromhex(r["fingerprint"]), r["split"])
               for r in self._records.values()
               if r.get("fingerprint") and not r.get("deleted")]
        for i in range(len(fps)):
            for j in range(i + 1, len(fps)):
                if fps[i][2] != fps[j][2] and hamming_distance(fps[i][1], fps[j][1]) <= NEAR_DUPE_MAX_HAMMING:
                    issues.append(f"near-duplicates {fps[i][0]} and {fps[j][0]} "
                                  f"in splits {fps[i][2]} and {fps[j][2]}")
        return {"issues": issues, "clean": not issues}
