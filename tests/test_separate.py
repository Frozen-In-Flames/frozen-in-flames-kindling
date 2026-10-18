"""Tests for kindling.assets.separate (vocal / accompaniment separation).

Method: classical DSP only (center-channel cue plus REPET-style repeating
background), no learned models. The eval builds synthetic mixtures with
KNOWN ground truth from the repo's own synth idioms, then reports
SDR/SIR/SAR improvement over the no-separation baseline. Numbers are
printed so the honest performance is visible, not just asserted.
"""

import numpy as np
import pytest

from kindling.assets.separate import (
    estimate_loop_period_frames,
    highpass,
    separate_vocals,
)
from kindling.assets.voice import analyze_reference

RATE = 22050
DUR = 16.0
LOOP_S = 2.0


def _synth_vocal(rate=RATE, seconds=DUR):
    """Vocal-like ground truth: harmonic lines with vibrato and slow
    glides, in three phrases with breath gaps. Each phrase has its own
    pitch contour, so per time-frequency bin the vocal is sparse across
    loop repetitions: the condition the repeating-background cue needs.
    Center-panned."""
    n = int(rate * seconds)
    t = np.arange(n) / rate
    sig = np.zeros(n)
    env = np.zeros(n)
    phrases = [
        (1.0, 3.0, 240.0, 0.22),
        (6.0, 8.5, 290.0, 0.30),
        (11.0, 14.0, 210.0, 0.18),
    ]
    for a, b, f_center, glide_rate in phrases:
        i0, i1 = int(a * rate), int(b * rate)
        tt = np.arange(i1 - i0) / rate
        f0 = f_center + 35.0 * np.sin(2 * np.pi * glide_rate * tt)
        vib = 4.0 * np.sin(2 * np.pi * 5.5 * tt)
        phase = np.cumsum(2 * np.pi * (f0 + vib) / rate)
        tone = np.zeros(i1 - i0)
        for h in range(1, 9):
            tone += np.sin(h * phase) / h
        tone = tone / (np.max(np.abs(tone)) + 1e-12)
        win = np.hanning(i1 - i0)
        sig[i0:i1] += tone * win * 0.5
        env[i0:i1] = np.maximum(env[i0:i1], win)
    sig = sig / (np.max(np.abs(sig)) + 1e-12) * 0.5
    return np.stack([sig, sig])


def _synth_loop(rate=RATE, seconds=DUR):
    """Accompaniment ground truth: a 2 s loop tiled to full length. Kick
    and bass centered, hats decorrelated wide. Repeats exactly, by design."""
    rng = np.random.default_rng(7)
    nl = int(rate * LOOP_S)
    loop = np.zeros(nl)
    for b in (0.0, 1.0):  # kick on 1 and 3
        i0, m = int(b * rate), int(0.25 * rate)
        tt = np.arange(m) / rate
        f = 120 * np.exp(-tt * 30) + 45
        ph = np.cumsum(2 * np.pi * f / rate)
        loop[i0:i0 + m] += np.sin(ph) * np.exp(-tt * 18)
    for e in np.arange(0, LOOP_S, 0.25):  # hats on eighths
        i0, m = int(e * rate), int(0.05 * rate)
        hp = np.diff(rng.standard_normal(m), prepend=0)
        loop[i0:i0 + m] += hp * np.exp(-np.arange(m) / (m * 0.2)) * 0.4
    for i, fq in enumerate([55.0, 55.0, 65.41, 49.0] * 2):  # bass line
        i0, m = int(i * 0.25 * rate), int(0.22 * rate)
        tt = np.arange(m) / rate
        tone = sum(np.sin(2 * np.pi * fq * h * tt) / h for h in (1, 2, 3))
        loop[i0:i0 + m] += tone * np.exp(-tt * 4) * 0.35
    loop = loop / (np.max(np.abs(loop)) + 1e-12) * 0.5
    tiled = np.tile(loop, int(seconds / LOOP_S))
    shimmer = rng.standard_normal(len(tiled)) * 0.02
    return np.stack([tiled + shimmer, tiled - shimmer])


def _mixture():
    vocal = _synth_vocal()
    acc = _synth_loop()
    mix = vocal + acc
    mix = mix / (np.max(np.abs(mix)) + 1e-12) * 0.89
    return mix, vocal, acc


def _decompose(estimate, target, interferer):
    """Simplified BSS eval: least-squares projection of the estimate onto
    the target and the known interferer. Returns (SDR, SIR, SAR) in dB."""
    e = np.asarray(estimate, float).ravel()
    s = np.asarray(target, float).ravel()
    nch = np.asarray(interferer, float).ravel()

    def db(x):
        return 10 * np.log10(x + 1e-12)

    s_proj = (np.dot(e, s) / (np.dot(s, s) + 1e-12)) * s
    resid = e - s_proj
    i_proj = (np.dot(resid, nch) / (np.dot(nch, nch) + 1e-12)) * nch
    artif = resid - i_proj
    sdr = db(np.sum(s_proj ** 2) / np.sum(resid ** 2))
    sir = db(np.sum(s_proj ** 2) / np.sum(i_proj ** 2))
    sar = db(np.sum((s_proj + i_proj) ** 2) / np.sum(artif ** 2))
    return sdr, sir, sar


def _mono(x):
    return np.asarray(x, float).mean(axis=0)


def test_separation_improves_vocal_sdr_and_sir():
    mix, vocal, acc = _mixture()
    v_est, _ = separate_vocals(mix, RATE)
    base = _decompose(_mono(mix), _mono(vocal), _mono(acc))
    got = _decompose(_mono(v_est), _mono(vocal), _mono(acc))
    print(f"\nvocal SDR: baseline {base[0]:.1f} dB -> separated {got[0]:.1f} dB "
          f"(+{got[0] - base[0]:.1f})")
    print(f"vocal SIR: baseline {base[1]:.1f} dB -> separated {got[1]:.1f} dB "
          f"(+{got[1] - base[1]:.1f})")
    print(f"vocal SAR: baseline {base[2]:.1f} dB -> separated {got[2]:.1f} dB")
    assert got[0] - base[0] >= 3.0, "separated vocal SDR must beat the mixture"
    assert got[1] - base[1] >= 6.0, "separated vocal SIR must beat the mixture"


def test_separation_improves_accompaniment_sdr():
    mix, vocal, acc = _mixture()
    _, a_est = separate_vocals(mix, RATE)
    base = _decompose(_mono(mix), _mono(acc), _mono(vocal))[0]
    got = _decompose(_mono(a_est), _mono(acc), _mono(vocal))[0]
    print(f"\naccomp SDR: baseline {base:.1f} dB -> separated {got:.1f} dB "
          f"(+{got - base:.1f})")
    assert got - base >= 3.0


def test_loop_period_detected():
    _, _, acc = _mixture()
    from scipy import signal as _sig
    _, _, z = _sig.stft(acc[0], window="hann", nperseg=2048, noverlap=1536,
                        boundary="zeros")
    mag = np.abs(z)
    freqs = np.fft.rfftfreq(2048, 1.0 / RATE)
    period = estimate_loop_period_frames(mag, 512, RATE, freqs)
    print(f"\ndetected loop period: {period} frames "
          f"({period * 512 / RATE:.2f}s)")
    # The kick band repeats every 1.0 s (kicks on 1 and 3, bass pattern
    # included): the dominant repetition rate of the accompaniment.
    assert period is not None
    assert abs(period * 512 / RATE - 1.0) < 0.3


def test_stereo_layout_and_sample_accurate_length():
    mix, _, _ = _mixture()
    v_est, a_est = separate_vocals(mix, RATE)
    assert v_est.shape == mix.shape == (2, int(RATE * DUR))
    assert a_est.shape == mix.shape
    # Estimates partition the mixture: they sum back to it.
    recon = v_est + a_est
    assert np.max(np.abs(recon - mix)) < 1e-6


def test_mono_input_works_repet_only():
    mix, vocal, acc = _mixture()
    v_est, a_est = separate_vocals(_mono(mix), RATE)
    assert v_est.shape == (int(RATE * DUR),)
    base = _decompose(_mono(mix), _mono(vocal), _mono(acc))[0]
    got = _decompose(v_est, _mono(vocal), _mono(acc))[0]
    print(f"\nmono vocal SDR: baseline {base:.1f} dB -> separated {got:.1f} dB")
    assert got > base, "REPET cue alone must still help on mono"


def test_deterministic():
    mix, _, _ = _mixture()
    v1, a1 = separate_vocals(mix, RATE)
    v2, a2 = separate_vocals(mix, RATE)
    assert np.array_equal(v1, v2) and np.array_equal(a1, a2)


def test_highpass_removes_rumble():
    n = RATE * 2
    t = np.arange(n) / RATE
    rumble = np.sin(2 * np.pi * 55 * t)
    out = highpass(rumble, RATE, 120.0)
    assert np.max(np.abs(out[int(RATE):])) < 0.05 * np.max(np.abs(rumble))


def test_analyze_reference_opt_in_reduces_bleed():
    mix, vocal, _ = _mixture()
    mono_mix = _mono(mix)
    mono_vocal = _mono(vocal)
    mixed = analyze_reference(mono_mix, RATE)
    assert "separation" not in mixed
    clean = analyze_reference(mono_vocal, RATE)
    sep = analyze_reference(mono_mix, RATE, separate_vocals=True, stereo=mix)
    assert sep["separation"]["applied"] is True
    assert sep["separation"]["method"] == "kindling.assets.separate.separate_vocals"
    c_mix = mixed["identity_vector"][2]
    c_sep = sep["identity_vector"][2]
    c_vocal = clean["identity_vector"][2]
    print(f"\nspectral centroid: mixed {c_mix:.0f} Hz, separated {c_sep:.0f} Hz, "
          f"true vocal {c_vocal:.0f} Hz")
    assert abs(c_sep - c_vocal) < abs(c_mix - c_vocal), \
        "separated analysis must be closer to the clean vocal (less bleed)"


def test_analyze_reference_default_unchanged():
    mix, _, _ = _mixture()
    a = analyze_reference(_mono(mix), RATE)
    b = analyze_reference(_mono(mix), RATE, separate_vocals=False)
    assert a == b
    assert "separation" not in b


def test_separate_vocals_needs_stereo_for_opt_in():
    mix, _, _ = _mixture()
    with pytest.raises(ValueError):
        analyze_reference(_mono(mix), RATE, separate_vocals=True)
