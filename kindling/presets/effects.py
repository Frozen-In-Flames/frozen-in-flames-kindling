"""Real DSP effects for preset rendering.

Small, honest implementations: biquad EQ, feedforward compressor,
feedback delay (space), and a stereo widener. These are the building
blocks the preset graph chains together.
"""

import math
from typing import Dict

import numpy as np


def biquad_lowshelf(sig: np.ndarray, rate: int, freq: float,
                    gain_db: float) -> np.ndarray:
    """One-pole lowshelf: lows scaled by the gain, highs untouched."""
    g = 10 ** (gain_db / 20.0)
    cutoff = 2 * math.pi * freq / rate
    alpha = cutoff / (cutoff + 1.0)
    lp = np.zeros_like(sig)
    lp[0] = sig[0]
    for i in range(1, len(sig)):
        lp[i] = lp[i - 1] + alpha * (sig[i] - lp[i - 1])
    return (sig - lp) + lp * g


def biquad_highshelf(sig: np.ndarray, rate: int, freq: float,
                     gain_db: float) -> np.ndarray:
    """One-pole highshelf: highs scaled by the gain, lows untouched."""
    g = 10 ** (gain_db / 20.0)
    cutoff = 2 * math.pi * freq / rate
    alpha = cutoff / (cutoff + 1.0)
    lp = np.zeros_like(sig)
    lp[0] = sig[0]
    for i in range(1, len(sig)):
        lp[i] = lp[i - 1] + alpha * (sig[i] - lp[i - 1])
    hp = sig - lp
    return (sig - hp) + hp * g


def compressor(sig: np.ndarray, rate: int, threshold_db: float,
               ratio: float, attack_ms: float = 5.0,
               release_ms: float = 100.0) -> np.ndarray:
    """Feedforward peak compressor with smooth envelopes."""
    attack = math.exp(-1.0 / (rate * attack_ms / 1000.0))
    release = math.exp(-1.0 / (rate * release_ms / 1000.0))
    env = 0.0
    gain = np.ones_like(sig)
    for i in range(len(sig)):
        level = abs(sig[i])
        env = level if level > env else env * release + level * (1 - release)
        env = env * attack + level * (1 - attack) if level > env else env
        if env <= 0:
            continue
        env_db = 20 * math.log10(env + 1e-9)
        if env_db > threshold_db:
            target_db = threshold_db + (env_db - threshold_db) / ratio
            gain[i] = 10 ** ((target_db - env_db) / 20.0)
    # Smooth the gain to avoid zipper noise.
    smooth = np.zeros_like(gain)
    smooth[0] = gain[0]
    coef = 0.999
    for i in range(1, len(gain)):
        smooth[i] = smooth[i - 1] * coef + gain[i] * (1 - coef)
    return sig * smooth


def delay_space(stereo: np.ndarray, rate: int, time_ms: float,
                feedback: float, mix: float) -> np.ndarray:
    """Feedback delay for space (mono-in, stereo spread)."""
    if stereo.ndim == 1:
        stereo = np.stack([stereo, stereo])
    d = max(1, int(rate * time_ms / 1000.0))
    out = stereo.copy()
    buf_l = np.zeros(d)
    buf_r = np.zeros(d)
    for i in range(stereo.shape[1]):
        idx = i % d
        dl_l = buf_l[idx]
        dl_r = buf_r[idx]
        inp = (stereo[0, i] + stereo[1, i]) / 2
        buf_l[idx] = inp + dl_l * feedback
        buf_r[idx] = inp + dl_r * feedback * 0.9
        out[0, i] = stereo[0, i] * (1 - mix) + dl_l * mix
        out[1, i] = stereo[1, i] * (1 - mix) + dl_r * mix
    return out


def stereo_widener(stereo: np.ndarray, width: float) -> np.ndarray:
    """Mid/side width control. width=1 is unchanged, >1 wider."""
    if stereo.ndim == 1:
        return np.stack([stereo, stereo])
    mid = (stereo[0] + stereo[1]) / 2
    side = (stereo[0] - stereo[1]) / 2
    side = side * width
    return np.stack([mid + side, mid - side])


def apply_effect_chain(stereo: np.ndarray, rate: int,
                       chain: list) -> np.ndarray:
    """Apply a list of effect dicts in order. Each: {"type", "params"}."""
    out = stereo.copy()
    for fx in chain:
        ftype = fx["type"]
        p = fx.get("params", {})
        if ftype == "lowshelf":
            out = np.stack([biquad_lowshelf(ch, rate, p.get("freq", 200),
                                            p.get("gain_db", 0))
                            for ch in out])
        elif ftype == "highshelf":
            out = np.stack([biquad_highshelf(ch, rate, p.get("freq", 8000),
                                             p.get("gain_db", 0))
                            for ch in out])
        elif ftype == "compressor":
            out = np.stack([compressor(ch, rate,
                                       p.get("threshold_db", -18),
                                       p.get("ratio", 2.0),
                                       p.get("attack_ms", 5.0),
                                       p.get("release_ms", 100.0))
                            for ch in out])
        elif ftype == "delay":
            out = delay_space(out, rate, p.get("time_ms", 120),
                              p.get("feedback", 0.3), p.get("mix", 0.2))
        elif ftype == "widener":
            out = stereo_widener(out, p.get("width", 1.0))
    # Safety normalize.
    peak = np.max(np.abs(out))
    if peak > 1.0:
        out = out / peak * 0.99
    return out
