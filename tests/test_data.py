"""Tests for Part 4 (Data pipeline), including the acceptance tests:
records traceable to source/license/processing versions, and a leakage
audit with zero cross-split duplicates."""

import math
import os
import struct
import wave

import pytest

from kindling.data import LicenseLedger, Pipeline, build_manifest, validate_record
from kindling.data.record import low_confidence_labels
from kindling.data.ledger import delete_record
from kindling.data import browser as data_browser
from kindling.data.pipeline import (
    assign_split,
    fingerprint,
    hamming_distance,
    sha256_of_file,
)

RATE = 44100


def write_wav(path, samples, rate=RATE):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h",
                                   *[max(-32768, min(32767, int(s * 32767)))
                                     for s in samples]))


def click_track(path, bpm=120.0, seconds=4.0):
    n = int(seconds * RATE)
    samples = [0.0] * n
    period = int(RATE * 60.0 / bpm)
    for start in range(0, n, period):
        for i in range(min(300, n - start)):
            samples[start + i] += 0.8 * (1 - i / 300)
    write_wav(path, samples)
    return path


def chord_pad(path, freqs, seconds=4.0):
    n = int(seconds * RATE)
    samples = [0.0] * n
    for f in freqs:
        for i in range(n):
            t = i / RATE
            samples[i] += 0.25 * math.sin(2 * math.pi * f * t) * min(1.0, t * 4)
    write_wav(path, samples)
    return path


def cleared_license():
    return {"status": "cleared", "terms": "test fixture", "training_allowed": True}


@pytest.fixture
def pipeline(tmp_path):
    return Pipeline(str(tmp_path / "ledger"))


def test_ingest_record_is_traceable(pipeline, tmp_path):
    path = click_track(str(tmp_path / "a.wav"))
    rid = pipeline.ingest({"path": path, "name": "demo",
                           "acquisition": "upload",
                           "license": cleared_license()})
    record = pipeline.record(rid)
    validate_record(record)
    # Acceptance: traceable to source, license status, processing versions.
    assert record["source"]["name"] == "demo"
    assert record["source"]["acquisition"] == "upload"
    assert record["license"]["status"] == "cleared"
    assert record["processing_versions"]["pipeline"] == "4.0.0"
    assert record["content_hash"].startswith("sha256:")
    assert record["split"] in ("train", "validate", "test")


def test_exact_duplicate_returns_same_record(pipeline, tmp_path):
    path = click_track(str(tmp_path / "a.wav"))
    r1 = pipeline.ingest({"path": path, "name": "demo", "license": cleared_license()})
    r2 = pipeline.ingest({"path": path, "name": "demo-copy", "license": cleared_license()})
    assert r1 == r2
    assert len(pipeline.all_records()) == 1


def test_near_duplicate_pinned_to_same_split(pipeline, tmp_path):
    p1 = click_track(str(tmp_path / "a.wav"))
    samples = []
    with wave.open(p1, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        samples = [v * 1.12 for v in struct.unpack(f"<{len(raw)//2}h", raw)]
    p2 = str(tmp_path / "b.wav")
    write_wav(p2, [s / 32768.0 for s in samples])
    r1 = pipeline.ingest({"path": p1, "name": "orig", "license": cleared_license()})
    r2 = pipeline.ingest({"path": p2, "name": "gain-bump", "license": cleared_license()})
    assert r1 != r2
    rec2 = pipeline.record(r2)
    assert any(f.startswith("near-duplicate-of:") for f in rec2["flags"])
    assert rec2["split"] == pipeline.record(r1)["split"]


def test_leakage_audit_clean(pipeline, tmp_path):
    for i in range(6):
        chord_pad(str(tmp_path / f"t{i}.wav"), [110.0 * (1 + i * 0.13), 220.0, 330.0])
        pipeline.ingest({"path": str(tmp_path / f"t{i}.wav"),
                         "name": f"t{i}", "license": cleared_license()})
    audit = pipeline.leakage_audit()
    assert audit["clean"], audit["issues"]


def test_assign_split_is_deterministic():
    h = "sha256:" + "ab" * 32
    assert assign_split(h) == assign_split(h)


def test_deletion_propagates(pipeline, tmp_path):
    path = click_track(str(tmp_path / "a.wav"))
    rid = pipeline.ingest({"path": path, "name": "demo", "license": cleared_license()})
    record = pipeline.record(rid)
    record["derived_asset_ids"] = ["voice_test@v1"]
    before = build_manifest(pipeline, "train")
    assert rid in before["record_ids"]
    handle = delete_record(pipeline, rid, reason="test")
    assert handle["cascaded_assets"] == ["voice_test@v1"]
    after = build_manifest(pipeline, "train")
    assert rid not in after["record_ids"]
    assert pipeline.record(rid)["allowed_uses"] == []


def test_provenance_queryable(pipeline, tmp_path):
    for i, lic in enumerate([cleared_license(),
                             {"status": "pending", "training_allowed": True},
                             {"status": "unknown", "training_allowed": False}]):
        chord_pad(str(tmp_path / f"q{i}.wav"), [110.0 + i * 17, 220.0])
        pipeline.ingest({"path": str(tmp_path / f"q{i}.wav"),
                         "name": "srcA" if i < 2 else "srcB", "license": lic})
    ledger = LicenseLedger(pipeline)
    assert len(ledger.by_source("srcA")) == 2
    assert len(ledger.by_license_status("cleared")) == 1
    assert ledger.license_summary()["cleared"] == 1
    train_manifest = build_manifest(pipeline, "train")
    eval_manifest = build_manifest(pipeline, "evaluate")
    # cleared -> train+evaluate; pending+training_allowed -> evaluate only
    assert len(train_manifest["record_ids"]) == 1
    assert len(eval_manifest["record_ids"]) == 2


def test_labels_carry_confidence_and_low_marked(pipeline, tmp_path):
    path = click_track(str(tmp_path / "a.wav"))
    rid = pipeline.ingest({"path": path, "name": "demo", "license": cleared_license()})
    record = pipeline.record(rid)
    for name, lab in record["labels"].items():
        assert "confidence" in lab and "method" in lab, name
        assert 0.0 <= lab["confidence"] <= 1.0
    low = low_confidence_labels(record)
    assert isinstance(low, list)
    assert record["quality_score"] > 0


def test_key_estimation_on_major_pad(pipeline, tmp_path):
    # A major: A2 110, E3 164.81, A3 220, C#4 277.18, E4 329.63
    path = chord_pad(str(tmp_path / "amaj.wav"),
                     [110.0, 164.81, 220.0, 277.18, 329.63], seconds=6.0)
    rid = pipeline.ingest({"path": path, "name": "amaj", "license": cleared_license()})
    key = pipeline.record(rid)["labels"]["key"]
    assert key["value"] in ("A major", "E major", "D major", "C# minor")
    assert key["confidence"] > 0.2


def test_tempo_label_on_click_track(pipeline, tmp_path):
    path = click_track(str(tmp_path / "a.wav"), bpm=120.0)
    rid = pipeline.ingest({"path": path, "name": "demo", "license": cleared_license()})
    tempo = pipeline.record(rid)["labels"]["tempo"]
    assert tempo["value"] == pytest.approx(120.0, abs=4.0)
    assert tempo["confidence"] > 0.3


def test_lyric_alignment_with_transcript(pipeline, tmp_path):
    path = click_track(str(tmp_path / "a.wav"), bpm=90.0, seconds=6.0)
    rid = pipeline.ingest({"path": path, "name": "demo",
                           "license": cleared_license(),
                           "transcript": ["la", "la", "la"]})
    alignment = pipeline.record(rid)["labels"]["lyric_alignment"]
    assert alignment["method"] == "vocal-band-onset-align"
    assert len(alignment["value"]) == 3


def test_browser_search_and_show(pipeline, tmp_path):
    path = click_track(str(tmp_path / "a.wav"))
    rid = pipeline.ingest({"path": path, "name": "demo", "license": cleared_license()})
    found = data_browser.search(pipeline, source="demo")
    assert [r["record_id"] for r in found] == [rid]
    shown = data_browser.show(pipeline, rid)
    assert shown["record_id"] == rid
    assert "labels" in shown and "failure_flags" in shown


def test_browser_html_report(pipeline, tmp_path):
    path = click_track(str(tmp_path / "a.wav"))
    rid = pipeline.ingest({"path": path, "name": "demo",
                           "license": cleared_license(),
                           "transcript": ["la", "la"]})
    out = str(tmp_path / "report.html")
    data_browser.html_report(pipeline, rid, "a.wav", out)
    assert os.path.exists(out)
    text = open(out).read()
    assert rid in text and "<audio" in text


def test_fingerprint_robust_to_gain(tmp_path):
    p1 = click_track(str(tmp_path / "a.wav"))
    from kindling.scene.audio_import import read_wav_mono
    import numpy as np
    a = np.asarray(read_wav_mono(p1)["samples"])
    fp1 = fingerprint(a, RATE)
    fp2 = fingerprint(a * 1.1, RATE)
    assert hamming_distance(fp1, fp2) <= 51
    fp3 = fingerprint(np.random.RandomState(0).randn(len(a)) * 0.1, RATE)
    assert hamming_distance(fp1, fp3) > 51


def test_sha256_of_file(tmp_path):
    path = click_track(str(tmp_path / "a.wav"))
    assert sha256_of_file(path).startswith("sha256:")
    assert len(sha256_of_file(path)) == 7 + 64
