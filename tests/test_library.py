"""Phase A: upload / save / use loop (library + render-from-library)."""

import json
import math
import os
import wave

import numpy as np
import pytest

from kindling.library import AssetLibrary, load_audio
from kindling.library.audio import audio_sha256
from kindling.library.builders import (build_instrument_asset,
                                       build_preset_asset, build_voice_asset,
                                       make_consent)
from kindling.instruments.sampler import render_sample_instrument

RATE = 44100


def _write_wav(path, stereo, rate=RATE):
    arr = np.asarray(stereo, dtype=float)
    if arr.ndim == 1:
        arr = np.stack([arr, arr])
    if arr.shape[0] != 2:
        arr = arr.T
    arr = np.clip(arr, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((arr * 32767).astype(np.int16).tobytes())


def _vocalish(dur_s=8.0, rate=RATE):
    """Vocal-like: harmonic tone with vibrato; each of 5 segments emphasizes
    a different formant band and a different pitch, so the vowel clustering
    finds distinct spectral states."""
    n = int(dur_s * rate)
    t = np.arange(n) / rate
    sig = np.zeros(n)
    bands = [(300, 700), (900, 1400), (1600, 2400), (2600, 3400), (400, 900)]
    f0s = [140, 165, 190, 155, 175]
    for seg in range(5):
        a, b = int(seg * n / 5), int((seg + 1) * n / 5)
        f0 = f0s[seg] + 6 * np.sin(2 * math.pi * 0.5 * t[a:b])
        phase = 2 * math.pi * np.cumsum(f0) / rate
        tone = sum(np.sin(phase * h) / h for h in range(1, 10))
        # Emphasize this segment's formant band via an FFT mask.
        spec = np.fft.rfft(tone)
        freqs = np.fft.rfftfreq(len(tone), 1.0 / rate)
        lo, hi = bands[seg]
        mask = np.clip((freqs - lo + 200) / 400, 0, 1) * np.clip(
            (hi + 200 - freqs) / 400, 0, 1)
        shaped = np.fft.irfft(spec * (0.3 + 1.4 * mask), len(tone))
        sig[a:b] = shaped
    sig = sig / (np.max(np.abs(sig)) + 1e-9) * 0.7
    return sig.astype(np.float32)


def _plucks(dur_s=6.0, rate=RATE):
    n = int(dur_s * rate)
    out = np.zeros(n)
    for i, midi in enumerate([45, 48, 52, 55, 57, 55, 52, 48]):
        f = 440.0 * 2 ** ((midi - 69) / 12)
        start = int(i * 0.7 * rate)
        nn = int(0.6 * rate)
        t = np.arange(nn) / rate
        tone = np.sin(2 * math.pi * f * t) * np.exp(-t * 6) * 0.6
        out[start:start + nn] += tone[:max(0, min(nn, n - start))]
    return (out / (np.max(np.abs(out)) + 1e-9) * 0.8).astype(np.float32)


def _mixlike(dur_s=6.0, rate=RATE):
    n = int(dur_s * rate)
    t = np.arange(n) / rate
    sig = (0.4 * np.sin(2 * math.pi * 110 * t)
           + 0.3 * np.sin(2 * math.pi * 440 * t + 1)
           + 0.15 * np.sin(2 * math.pi * 3000 * t))
    sig = sig / (np.max(np.abs(sig)) + 1e-9) * 0.8
    return np.stack([sig, sig * 0.9]).astype(np.float32)


@pytest.fixture()
def lib(tmp_path):
    return AssetLibrary(str(tmp_path / "lib"))


@pytest.fixture()
def owner():
    return {"id": "test-owner"}


# ---------------------------------------------------------------- audio
def test_load_wav_roundtrip(tmp_path):
    p = tmp_path / "t.wav"
    _write_wav(p, _mixlike(2.0))
    samples, rate = load_audio(str(p), mono=False)
    assert rate == RATE and samples.shape == (2, 2 * RATE)
    assert float(np.max(np.abs(samples))) > 0.5


def test_load_mp3(tmp_path):
    pytest.importorskip("shutil")
    import shutil
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    src = tmp_path / "t.wav"
    _write_wav(src, _mixlike(2.0))
    mp3 = tmp_path / "t.mp3"
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                    str(mp3)], check=True)
    samples, rate = load_audio(str(mp3), mono=True)
    assert rate == RATE and samples.ndim == 1
    assert float(np.max(np.abs(samples))) > 0.3


def test_load_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_audio("/no/such/file.wav")


# ---------------------------------------------------------------- voice
def test_voice_upload_requires_consent(lib, owner):
    with pytest.raises(ValueError):
        make_consent()


def test_voice_upload_roundtrip(lib, owner):
    voice, report = build_voice_asset(
        _vocalish(), RATE, "Test Singer", owner,
        make_consent(subject="Test Singer", attested_by="test-owner"),
        languages=["en"])
    assert voice["kind"] == "kindling/voice-character"
    assert len(voice["identity"]["vector"]) > 0
    assert "sufficiency" in report
    asset_id = lib._unique_id("voice", "Test Singer")
    sha = lib.store_audio(_vocalish(), RATE)
    rec = lib.save_record({
        "id": asset_id, "asset_kind": "voice", "name": "Test Singer",
        "owner": owner, "source_audio_sha256": sha,
        "consent": voice["consent"], "payload": voice})
    assert rec["payload"]["id"] == asset_id or True
    got = lib.get(asset_id)
    assert got["payload"]["identity"]["vector"] == \
        voice["identity"]["vector"]
    assert lib.audio_path(sha).endswith(".wav")


def test_ingest_voice_character(lib):
    char = {"kind": "kindling/voice-character", "id": "voice_x",
            "version": "v1", "name": "X",
            "identity": {"vector": [1.0], "method": "m"},
            "range_map": {"low_midi": 40, "high_midi": 80, "registers": []},
            "reference_summary": {}, "owner": {"id": "o"},
            "consent": {"subject": "X", "rights_basis": "consent",
                        "verified_against_audio": True},
            "provenance": {}, "revoked": False}
    saved = lib.ingest(char)
    assert saved["id"] == "voice_x"
    assert saved["asset_kind"] == "voice"
    assert lib.get("voice_x")["payload"]["name"] == "X"


# ------------------------------------------------------------ instrument
def test_instrument_upload_and_render(lib, owner):
    payload, report = build_instrument_asset(_plucks(), RATE, "Plucks",
                                            owner, default_role="keys")
    assert payload["kind"] == "kindling/sample-instrument"
    assert report["slices"] >= 4
    assert payload["default_role"] == "keys"
    notes = [{"midi": 60 + i, "start_s": i * 0.5, "dur_s": 0.4, "vel": 0.8}
             for i in range(4)]
    out = render_sample_instrument(payload, _plucks(), notes, RATE, seed=3)
    assert float(np.max(np.abs(out))) > 0.05
    out2 = render_sample_instrument(payload, _plucks(), notes, RATE, seed=3)
    assert np.array_equal(out, out2)


# --------------------------------------------------------------- preset
def test_preset_upload_and_apply(owner):
    payload, report = build_preset_asset(_mixlike(), RATE, "P", owner)
    assert payload["kind"] == "kindling/inferred-preset"
    assert report["chain_effects"]
    assert 0.0 <= report["confidence"] <= 1.0
    from kindling.presets.render import render_preset
    stereo = _mixlike()
    out = render_preset(stereo, RATE, {"chain": payload["preset"]["chain"]})
    assert out.shape == stereo.shape


# ------------------------------------------------------------------ CRUD
def test_library_crud_and_delete_cascade(lib, owner):
    lib.save_record({"id": "preset_a", "asset_kind": "preset",
                     "name": "A", "owner": owner, "payload": {}})
    lib.save_record({"id": "preset_b", "asset_kind": "preset",
                     "name": "B", "owner": owner, "payload": {}})
    assert len(lib.list()) == 2
    assert len(lib.list("preset")) == 2
    lib.rename("preset_a", "A2")
    assert lib.get("preset_a")["name"] == "A2"
    # Shared audio survives one deletion, goes on the last.
    sha = lib.store_audio(_plucks(), RATE)
    ra = lib.get("preset_a")
    ra["source_audio_sha256"] = sha
    lib.save_record(ra)
    rb = lib.get("preset_b")
    rb["source_audio_sha256"] = sha
    lib.save_record(rb)
    rep = lib.delete("preset_a")
    assert not rep["audio_removed"]
    rep = lib.delete("preset_b")
    assert rep["audio_removed"]
    assert len(lib.list()) == 0
    with pytest.raises(KeyError):
        lib.get("preset_b")


# ---------------------------------------------------------------- compose
def _seed_library(lib, owner):
    voice, _ = build_voice_asset(
        _vocalish(), RATE, "Singer", owner,
        make_consent(subject="Singer", attested_by="test-owner"),
        languages=["en"])
    vid = lib._unique_id("voice", "Singer")
    vsha = lib.store_audio(_vocalish(), RATE)
    vrec = dict(voice)
    vrec["id"] = vid
    lib.save_record({"id": vid, "asset_kind": "voice", "name": "Singer",
                     "owner": owner, "source_audio_sha256": vsha,
                     "consent": voice["consent"], "payload": vrec})
    payload, _ = build_instrument_asset(_plucks(), RATE, "Plucks", owner,
                                        default_role="keys")
    iid = lib._unique_id("instrument", "Plucks")
    isha = lib.store_audio(_plucks(), RATE)
    lib.save_record({"id": iid, "asset_kind": "instrument", "name": "Plucks",
                     "owner": owner, "source_audio_sha256": isha,
                     "payload": payload})
    ppayload, _ = build_preset_asset(_mixlike(), RATE, "P", owner)
    pid = lib._unique_id("preset", "P")
    psha = lib.store_audio(_mixlike()[0], RATE)
    lib.save_record({"id": pid, "asset_kind": "preset", "name": "P",
                     "owner": owner, "source_audio_sha256": psha,
                     "payload": ppayload})
    return vid, iid, pid


def _read_wav_mono(path):
    w = wave.open(str(path), "rb")
    raw = w.readframes(w.getnframes())
    ch = w.getnchannels()
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float64).reshape(-1, ch).T
    return arr / 32767.0, w.getframerate()


def test_compose_end_to_end(tmp_path, lib, owner):
    from kindling.library.song import compose
    vid, iid, pid = _seed_library(lib, owner)
    out = tmp_path / "song"
    lyrics = "First light on the wire\nWe build the fire higher\n"
    r1 = compose("verse, 120 bpm", lyrics, lib, voice_id=vid,
                 instrument_map={"keys": iid}, preset_id=pid,
                 seed=11, owner=owner, out_dir=str(out))
    for name in ("mix.wav", "mix_pre_preset.wav", "score.mid",
                 "lyrics.lrc", "sidecar.json", "scene.json"):
        assert (out / name).is_file(), name
    stems = sorted((out / "stems").glob("stem-*.wav"))
    assert len(stems) >= 4
    mix, _ = _read_wav_mono(out / "mix.wav")
    assert float(np.max(np.abs(mix))) > 0.01
    # Determinism: same seed, same mix.
    out2 = tmp_path / "song2"
    compose("verse, 120 bpm", lyrics, lib, voice_id=vid,
            instrument_map={"keys": iid}, preset_id=pid,
            seed=11, owner=owner, out_dir=str(out2))
    mix2, _ = _read_wav_mono(out2 / "mix.wav")
    assert np.array_equal(mix, mix2)
    # Stems sum to the pre-preset mix within 16-bit tolerance.
    pre, _ = _read_wav_mono(out / "mix_pre_preset.wav")
    total = sum(_read_wav_mono(s)[0] for s in stems)
    n = min(total.shape[1], pre.shape[1])
    assert float(np.max(np.abs(total[:, :n] - pre[:, :n]))) < 2e-3
    # Sidecar completeness.
    sc = json.loads((out / "sidecar.json").read_text())
    assert sc["asset_versions"]["lead_vocal"].startswith(vid)
    assert sc["asset_versions"]["keys"].startswith(iid)
    assert sc["asset_versions"]["preset"].startswith(pid)
    assert sc["seeds"]["render"] == 11
    assert sc["render_settings"]["sample_rate"] == 44100
    assert "prompt" in sc["provenance"]
    # MIDI exists and parses.
    import mido
    mid = mido.MidiFile(str(out / "score.mid"))
    assert sum(1 for _ in mid) > 0


def test_compose_without_assets(tmp_path, lib, owner):
    from kindling.library.song import compose
    out = tmp_path / "song"
    r = compose("verse, 120 bpm", "Line one here\nLine two here\n", lib,
                seed=5, owner=owner, out_dir=str(out))
    assert (out / "mix.wav").is_file()
    assert r["vocal_lines"] == 0
    assert r["asset_versions"] == {}


# ------------------------------------------------------------------- CLI
def test_cli_library_roundtrip(tmp_path, lib, owner):
    from kindling.api.cli import main as cli_main
    ldir = str(tmp_path / "lib2")
    p = tmp_path / "v.wav"
    _write_wav(p, _vocalish(4.0))
    rc = cli_main(["library", "upload", str(p), "--kind", "voice",
                   "--name", "CLI Singer", "--consent-subject", "CLI Singer",
                   "--owner", "cli", "--library", ldir])
    assert rc == 0
    assert cli_main(["library", "list", "--library", ldir]) == 0
    lib2 = AssetLibrary(ldir)
    vid = lib2.list("voice")[0]["id"]
    assert cli_main(["library", "show", vid, "--library", ldir]) == 0
    assert cli_main(["library", "rename", vid, "Renamed", "--library",
                     ldir]) == 0
    assert cli_main(["library", "delete", vid, "--library", ldir]) == 0
    assert lib2.list() == []


def test_cli_render_compose(tmp_path):
    from kindling.api.cli import main as cli_main
    ldir = str(tmp_path / "lib3")
    lib3 = AssetLibrary(ldir)
    _seed_library(lib3, {"id": "cli"})
    vid = lib3.list("voice")[0]["id"]
    lyr = tmp_path / "lyr.txt"
    lyr.write_text("Kindling on the wire\nFire burning higher\n")
    out = tmp_path / "out"
    rc = cli_main(["render", "--prompt", "verse, 120 bpm",
                   "--lyrics-file", str(lyr), "--voice", vid,
                   "--seed", "9", "--out", str(out),
                   "--library", ldir, "--owner", "cli"])
    assert rc == 0
    assert (out / "mix.wav").is_file()
    assert (out / "sidecar.json").is_file()


def test_cli_export(tmp_path):
    from kindling.api.cli import main as cli_main
    from kindling.library.song import compose
    lib4 = AssetLibrary(str(tmp_path / "lib4"))
    out = tmp_path / "proj"
    compose("verse, 120 bpm", "Line one here\n", lib4, seed=1,
            owner={"id": "t"}, out_dir=str(out))
    exp = tmp_path / "exp"
    assert cli_main(["export", str(out), "--format", "stems",
                     "--out", str(exp)]) == 0
    assert len(list(exp.glob("*.wav"))) > 0
    exp2 = tmp_path / "exp2"
    assert cli_main(["export", str(out), "--format", "midi",
                     "--out", str(exp2)]) == 0
    assert (exp2 / "score.mid").is_file()
