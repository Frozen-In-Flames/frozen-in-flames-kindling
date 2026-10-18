"""Reference synthesizers: teacher (high-detail) and student (distilled).

The teacher is the quality reference: oversampled, rich excitation,
expensive. The student is the deployable model: same interface, fewer
resources, parameters fitted to match the teacher (see distill.py).

Both are deterministic given (notes, controls, seed). Neither is a
neural network; they are the procedural stand-ins behind the
instrument interfaces, honest about what they are.
"""

import math
from typing import Dict, List

import numpy as np


def _midi_to_freq(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69.0) / 12.0)


class TeacherGuitar:
    """High-detail Karplus-Strong plucked string (teacher)."""

    def render(self, notes: List[Dict], controls: Dict, rate: int,
               seed: int = 0) -> np.ndarray:
        # notes: [{"midi", "start_s", "dur_s", "vel"}]
        # controls: {"tone", "attack", "space"}
        total = max((n["start_s"] + n["dur_s"] for n in notes), default=0.0)
        out = np.zeros(int(total * rate) + rate)
        rng = np.random.default_rng(seed)
        tone = controls.get("tone", 0.5)
        for n in notes:
            freq = _midi_to_freq(n["midi"])
            period = max(2, int(rate / freq))
            dur_n = int(n["dur_s"] * rate)
            # Rich excitation: noise burst shaped by attack control.
            excite_len = period * 4
            exc = rng.standard_normal(excite_len)
            attack = controls.get("attack", 0.4)
            exc *= np.exp(-np.arange(excite_len) / (excite_len * (0.2 + attack)))
            # Karplus-Strong with tone-dependent damping.
            damp = 0.996 - 0.02 * tone
            buf = exc[:period].copy()
            sig = np.zeros(dur_n)
            idx = 0
            for i in range(dur_n):
                sig[i] = buf[idx]
                nxt = (buf[idx] + buf[(idx + 1) % period]) * 0.5 * damp
                buf[idx] = nxt
                idx = (idx + 1) % period
            # Velocity and simple decay envelope.
            env = np.exp(-np.arange(dur_n) / (rate * n["dur_s"] * 0.8))
            env = np.minimum(env * 3.0, 1.0)
            sig = sig * env * n["vel"]
            start = int(n["start_s"] * rate)
            out[start:start + dur_n] += sig
        # Space: simple feedback delay.
        space = controls.get("space", 0.2)
        if space > 0:
            d = int(rate * 0.09)
            wet = np.zeros_like(out)
            wet[d:] = out[:-d] * space * 0.4
            out = out + wet
        peak = np.max(np.abs(out))
        return out / peak * 0.9 if peak > 0 else out


class StudentGuitar:
    """Distilled guitar: same interface, cheaper excitation, fitted params.

    Fitted parameters (set by distill.py): damping_bias, excite_decay.
    """

    def __init__(self, damping_bias: float = 0.0, excite_decay: float = 1.0):
        self.damping_bias = damping_bias
        self.excite_decay = excite_decay

    def render(self, notes: List[Dict], controls: Dict, rate: int,
               seed: int = 0) -> np.ndarray:
        total = max((n["start_s"] + n["dur_s"] for n in notes), default=0.0)
        out = np.zeros(int(total * rate) + rate)
        rng = np.random.default_rng(seed)
        tone = controls.get("tone", 0.5)
        for n in notes:
            freq = _midi_to_freq(n["midi"])
            period = max(2, int(rate / freq))
            dur_n = int(n["dur_s"] * rate)
            # Cheap excitation: single noise period.
            exc = rng.standard_normal(period)
            damp = 0.996 - 0.02 * tone + self.damping_bias
            damp = min(0.999, max(0.9, damp))
            buf = exc.copy()
            sig = np.zeros(dur_n)
            idx = 0
            decay = self.excite_decay
            for i in range(dur_n):
                sig[i] = buf[idx]
                nxt = (buf[idx] + buf[(idx + 1) % period]) * 0.5 * damp
                buf[idx] = nxt * decay
                idx = (idx + 1) % period
            env = np.exp(-np.arange(dur_n) / (rate * n["dur_s"] * 0.8))
            env = np.minimum(env * 3.0, 1.0)
            sig = sig * env * n["vel"]
            start = int(n["start_s"] * rate)
            out[start:start + dur_n] += sig
        space = controls.get("space", 0.2)
        if space > 0:
            d = int(rate * 0.09)
            wet = np.zeros_like(out)
            wet[d:] = out[:-d] * space * 0.4
            out = out + wet
        peak = np.max(np.abs(out))
        return out / peak * 0.9 if peak > 0 else out


class TeacherBass:
    """High-detail filtered saw bass (teacher)."""

    def render(self, notes: List[Dict], controls: Dict, rate: int,
               seed: int = 0) -> np.ndarray:
        total = max((n["start_s"] + n["dur_s"] for n in notes), default=0.0)
        out = np.zeros(int(total * rate) + rate)
        tone = controls.get("tone", 0.6)
        for n in notes:
            freq = _midi_to_freq(n["midi"])
            dur_n = int(n["dur_s"] * rate)
            t = np.arange(dur_n) / rate
            # Saw from additive harmonics (16 partials).
            sig = sum(np.sin(2 * math.pi * freq * h * t) / h
                      for h in range(1, 17))
            # Tone-dependent lowpass (one-pole).
            cutoff = 0.05 + 0.3 * tone
            y = np.zeros(dur_n)
            y[0] = sig[0]
            for i in range(1, dur_n):
                y[i] = y[i - 1] + cutoff * (sig[i] - y[i - 1])
            attack = controls.get("attack", 0.7)
            a_n = max(1, int(rate * 0.005 * (1.2 - attack)))
            env = np.ones(dur_n)
            env[:a_n] = np.linspace(0, 1, a_n)
            env = env * np.exp(-t / (n["dur_s"] * 1.5))
            sig = y * env * n["vel"]
            start = int(n["start_s"] * rate)
            out[start:start + dur_n] += sig
        peak = np.max(np.abs(out))
        return out / peak * 0.9 if peak > 0 else out


class StudentBass:
    """Distilled bass: 6 partials, fitted filter param."""

    def __init__(self, filter_bias: float = 0.0):
        self.filter_bias = filter_bias

    def render(self, notes: List[Dict], controls: Dict, rate: int,
               seed: int = 0) -> np.ndarray:
        total = max((n["start_s"] + n["dur_s"] for n in notes), default=0.0)
        out = np.zeros(int(total * rate) + rate)
        tone = controls.get("tone", 0.6)
        for n in notes:
            freq = _midi_to_freq(n["midi"])
            dur_n = int(n["dur_s"] * rate)
            t = np.arange(dur_n) / rate
            sig = sum(np.sin(2 * math.pi * freq * h * t) / h
                      for h in range(1, 7))
            cutoff = 0.05 + 0.3 * tone + self.filter_bias
            cutoff = min(0.5, max(0.01, cutoff))
            y = np.zeros(dur_n)
            y[0] = sig[0]
            for i in range(1, dur_n):
                y[i] = y[i - 1] + cutoff * (sig[i] - y[i - 1])
            attack = controls.get("attack", 0.7)
            a_n = max(1, int(rate * 0.005 * (1.2 - attack)))
            env = np.ones(dur_n)
            env[:a_n] = np.linspace(0, 1, a_n)
            env = env * np.exp(-t / (n["dur_s"] * 1.5))
            sig = y * env * n["vel"]
            start = int(n["start_s"] * rate)
            out[start:start + dur_n] += sig
        peak = np.max(np.abs(out))
        return out / peak * 0.9 if peak > 0 else out
