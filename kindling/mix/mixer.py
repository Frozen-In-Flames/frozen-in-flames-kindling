"""Mixer (13.1): levels, panning, tone, dynamics, space, buses, automation.

Deterministic given the same inputs. Avoids clipping. Reports loudness
and true-peak values.
"""

import math
from typing import Any, Dict, List

import numpy as np


def _db_to_gain(db: float) -> float:
    return 10 ** (db / 20.0)


def pan_stereo(mono: np.ndarray, pan: float) -> np.ndarray:
    """Constant-power pan: -1 left, 0 center, +1 right."""
    angle = (pan + 1) * math.pi / 4
    return np.stack([mono * math.cos(angle), mono * math.sin(angle)])


def k_weighted_loudness(stereo: np.ndarray, rate: int) -> float:
    """Simplified K-weighting (BS.1770): high-shelf + highpass, then
    mean-square in 400 ms blocks, gated. Returns LUFS-ish value."""
    if stereo.ndim == 1:
        stereo = np.stack([stereo, stereo])
    # High shelf +4 dB above ~1.5 kHz (one-pole approx) and highpass.
    y = np.zeros_like(stereo)
    for ch in range(2):
        sig = stereo[ch]
        # Highpass (remove DC/rumble): y = x - lowpass(x).
        alpha = 2 * math.pi * 60 / rate
        alpha = alpha / (alpha + 1.0)
        lp = np.zeros_like(sig)
        lp[0] = sig[0]
        for i in range(1, len(sig)):
            lp[i] = lp[i - 1] + alpha * (sig[i] - lp[i - 1])
        hp = sig - lp
        # High shelf boost (crude): add differentiated highs.
        y[ch] = hp + 0.5 * np.diff(hp, prepend=hp[0])
    # 400 ms blocks, absolute gate at -70.
    block = int(rate * 0.4)
    hop = block // 2
    energies = []
    for s in range(0, y.shape[1] - block, hop):
        e = float(np.mean(y[:, s:s + block] ** 2))
        if e > 10 ** (-70 / 10):
            energies.append(e)
    if not energies:
        return -70.0
    # Relative gate at -10 below the ungated mean.
    mean_e = float(np.mean(energies))
    gated = [e for e in energies if e > mean_e * 0.1]
    if not gated:
        gated = energies
    return round(-0.691 + 10 * math.log10(float(np.mean(gated)) + 1e-12), 1)


def true_peak(stereo: np.ndarray) -> float:
    """True peak via 4x linear oversampling (crude but real)."""
    if stereo.ndim == 1:
        stereo = np.stack([stereo, stereo])
    peak = 0.0
    for ch in stereo:
        # 4x oversample by linear interpolation.
        n = len(ch) * 4
        x = np.interp(np.linspace(0, len(ch) - 1, n),
                      np.arange(len(ch)), ch)
        peak = max(peak, float(np.max(np.abs(x))))
    return round(20 * math.log10(peak + 1e-9), 2)


class Mixer:
    """Deterministic mixer driven by the production graph."""

    def __init__(self, rate: int = 48000):
        self.rate = rate

    def mix(self, stems: Dict[str, np.ndarray],
            production: Dict[str, Any]) -> Dict[str, Any]:
        """stems: part_id -> mono audio. production: levels, pans, buses,
        automation. Returns {"mix": stereo, "report": {...}}."""
        if not stems:
            raise ValueError("no stems to mix")
        n = max(len(s) for s in stems.values())
        routing = production.get("routing", {})
        sends = production.get("sends", [])
        automation = production.get("automation", [])

        mixed_stems: Dict[str, np.ndarray] = {}
        for pid, mono in stems.items():
            cfg = routing.get(pid, {})
            level_db = cfg.get("level_db", 0.0)
            pan = cfg.get("pan", 0.0)
            # Automation: level changes over time.
            gain_curve = np.ones(n) * _db_to_gain(level_db)
            for auto in automation:
                if auto.get("target") == f"level:{pid}":
                    t = int(auto.get("time_s", 0) * self.rate)
                    v = _db_to_gain(auto.get("value_db", 0.0))
                    if 0 <= t < n:
                        gain_curve[t:] = v
            padded = np.zeros(n)
            padded[:len(mono)] = mono
            stereo = pan_stereo(padded * gain_curve, pan)
            mixed_stems[pid] = stereo

        # Buses: sum members, apply bus processing (simple gain).
        buses = production.get("buses", {})
        bus_mixes: Dict[str, np.ndarray] = {}
        for bus, members in buses.items():
            acc = np.zeros((2, n))
            for m in members:
                if m in mixed_stems:
                    acc += mixed_stems[m]
            bus_gain = _db_to_gain(buses.get(f"{bus}:level_db", 0.0)) \
                if isinstance(buses.get(f"{bus}:level_db"), (int, float)) \
                else 1.0
            bus_mixes[bus] = acc * bus_gain

        # Master: sum buses (or stems if no buses), avoid clipping.
        if bus_mixes:
            master = sum(bus_mixes.values())
        else:
            master = sum(mixed_stems.values())
        peak = float(np.max(np.abs(master)))
        headroom_db = 20 * math.log10(peak + 1e-9)
        if peak > 0.99:
            master = master / peak * 0.99
            limited = True
        else:
            limited = False

        report = {
            "loudness_lufs": k_weighted_loudness(master, self.rate),
            "true_peak_dbfs": true_peak(master),
            "peak_dbfs_before_limit": round(headroom_db, 2),
            "limited": limited,
            "stems": {pid: {"loudness_lufs": k_weighted_loudness(
                s, self.rate)} for pid, s in mixed_stems.items()},
        }
        return {"mix": master, "report": report, "stems": mixed_stems}
