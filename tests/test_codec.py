"""Tests for Part 5 (Audio representation), including the acceptance tests:
objective checks for spectral error, transient smearing, stereo correlation,
and loudness drift, plus encode-edit-decode round trips with no seams at
region boundaries."""

import numpy as np
import pytest

from kindling.codec import FramedCodec, decode_tokens, encode_audio, evaluate_codec
from kindling.codec.eval import (
    loudness_drift_db,
    seam_energy,
    spectral_error_db,
    stereo_correlation,
    test_signals,
    transient_preservation,
)


@pytest.fixture
def stereo_440():
    rate = 48000
    t = np.arange(rate * 2) / rate
    mono = 0.6 * np.sin(2 * np.pi * 440 * t)
    return np.stack([mono, mono * 0.7], axis=1), rate


def test_hifi_round_trip_near_lossless(stereo_440):
    stereo, rate = stereo_440
    codec = FramedCodec(rate="hifi")
    recon = codec.decode(codec.encode({"samples": stereo, "sample_rate": rate}))["samples"]
    assert np.max(np.abs(stereo - recon)) < 1.0 / 32767 + 1e-12


def test_draft_is_smaller_and_lossy(stereo_440):
    stereo, rate = stereo_440
    hifi = FramedCodec(rate="hifi").encode({"samples": stereo, "sample_rate": rate})
    draft = FramedCodec(rate="draft").encode({"samples": stereo, "sample_rate": rate})
    hifi_bytes = sum(len(f) for f in hifi["frames"])
    draft_bytes = sum(len(f) for f in draft["frames"])
    assert draft_bytes < hifi_bytes * 0.55  # base64 padding breaks exact 2:1
    assert FramedCodec(rate="draft").compression_ratio == 2.0
    recon = FramedCodec(rate="draft").decode(draft)["samples"]
    assert np.max(np.abs(stereo - recon)) > 1e-4  # genuinely lossy


def test_region_decode_matches_full_decode(stereo_440):
    # Acceptance: encode-edit-decode round trips show no seams at region
    # boundaries. Frame-aligned regions are bit-exact.
    stereo, rate = stereo_440
    for codec_rate in ("hifi", "draft"):
        codec = FramedCodec(rate=codec_rate)
        tokens = codec.encode({"samples": stereo, "sample_rate": rate})
        full = codec.decode(tokens)["samples"]
        region = codec.decode_region(tokens, 1.0, 1.5)
        start = region["region_start_sample"]
        assert start == (int(1.0 * rate) // 2048) * 2048  # frame containing 1.0s
        assert seam_energy(full, region["samples"], start) == 0.0


def test_region_decode_rejects_wrong_rate(stereo_440):
    stereo, rate = stereo_440
    tokens = FramedCodec(rate="hifi").encode({"samples": stereo, "sample_rate": rate})
    with pytest.raises(ValueError):
        FramedCodec(rate="draft").decode(tokens)


def test_stereo_image_preserved(stereo_440):
    stereo, rate = stereo_440
    for codec_rate in ("hifi", "draft"):
        codec = FramedCodec(rate=codec_rate)
        recon = codec.decode(codec.encode({"samples": stereo, "sample_rate": rate}))["samples"]
        scorr = stereo_correlation(stereo, recon)
        assert scorr["left"] > 0.99
        assert scorr["stereo_diff"] > 0.99


def test_multitrack_round_trip(stereo_440):
    stereo, rate = stereo_440
    codec = FramedCodec(rate="hifi")
    parts = {"drums": {"samples": stereo, "sample_rate": rate},
             "bass": {"samples": stereo * 0.5, "sample_rate": rate}}
    tokens = codec.encode_multitrack(parts)
    back = codec.decode_multitrack(tokens)
    assert set(back.keys()) == {"drums", "bass"}
    assert np.max(np.abs(back["drums"]["samples"] - stereo)) < 1e-4
    one = codec.decode_multitrack(tokens, names=["bass"])
    assert set(one.keys()) == {"bass"}


def test_mono_upmixed_to_stereo():
    rate = 48000
    mono = np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 0.5
    codec = FramedCodec(rate="hifi")
    recon = codec.decode(codec.encode({"samples": mono, "sample_rate": rate}))["samples"]
    assert recon.shape == (rate, 2)


def test_convenience_functions(stereo_440):
    stereo, rate = stereo_440
    tokens = encode_audio(stereo, sample_rate=rate, rate="draft")
    assert tokens["rate"] == "draft"
    recon = decode_tokens(tokens)["samples"]
    assert recon.shape == stereo.shape


def test_full_battery_hifi_passes():
    report = evaluate_codec(FramedCodec(rate="hifi"))
    assert report["passed"]
    assert set(report["signals"].keys()) == {"drums", "vocals", "piano", "dense_mix", "quiet"}


def test_full_battery_draft_passes():
    report = evaluate_codec(FramedCodec(rate="draft"))
    assert report["passed"]


def test_metrics_are_honest():
    # Identical signals score perfectly; silence is not punished.
    rate = 48000
    t = np.arange(rate) / rate
    sig = np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1) * 0.5
    assert spectral_error_db(sig[:, 0], sig[:, 0]) == 0.0
    assert transient_preservation(sig[:, 0], sig[:, 0], rate) == 1.0
    assert loudness_drift_db(sig[:, 0], sig[:, 0], rate) == 0.0
    scorr = stereo_correlation(sig, sig)
    assert scorr["left"] == pytest.approx(1.0)


def test_transient_metric_detects_smearing():
    rate = 48000
    n = rate * 2
    rng = np.random.RandomState(3)
    clicks = np.zeros(n)
    clicks[::rate // 2] = 1.0
    smeared = np.convolve(clicks, np.ones(2000) / 2000, mode="same")
    sharp = transient_preservation(clicks, clicks, rate)
    dull = transient_preservation(clicks, smeared, rate)
    assert sharp == pytest.approx(1.0)
    assert dull < sharp
