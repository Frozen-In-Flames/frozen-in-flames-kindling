"""Pinning and reproducibility levels (15.2, 15.3).

Every render records hashes of the software that produced it. A render
MUST be reproducible from its recorded inputs. Levels:
- Level A: bit-exact on pinned software and hardware.
- Level B: perceptually equivalent across hardware.
Never claim a level you have not tested.
"""

import hashlib
import importlib
import inspect
from typing import Any, Dict

import numpy as np


def hash_component(module_name: str) -> str:
    """SHA256 of a component's source (weights/tokenizer/engine/mixer)."""
    try:
        mod = importlib.import_module(module_name)
        src = inspect.getsource(mod)
    except (ImportError, OSError, TypeError):
        src = module_name
    return hashlib.sha256(src.encode()).hexdigest()[:16]


def pin_render_inputs() -> Dict[str, str]:
    """Record hashes for every render (15.2)."""
    return {
        "renderer": hash_component("kindling.planning.renderer"),
        "mixer": hash_component("kindling.mix.mixer"),
        "preset_engine": hash_component("kindling.presets.effects"),
        "tokenizer": hash_component("kindling.vocals.g2p"),
        "kindling_version": __import__("kindling").__version__,
    }


def check_reproducibility(before: np.ndarray, after: np.ndarray,
                          rate: int) -> Dict[str, Any]:
    """Compare a re-render to the original. Declares the achieved level.

    Level A: bit-exact (sample-identical).
    Level B: perceptually equivalent (< 1 dB mean spectral distance).
    Otherwise: not reproducible at the declared level.
    """
    a = np.asarray(before, dtype=float).ravel()
    b = np.asarray(after, dtype=float).ravel()
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    if np.array_equal(a, b):
        return {"level": "A", "bit_exact": True, "distance_db": 0.0}
    # Perceptual distance (gated: only bins with significant energy).
    win = int(rate * 0.05)
    dists = []
    for s in range(0, n - win, win // 2):
        sa = np.abs(np.fft.rfft(a[s:s + win] * np.hanning(win))) + 1e-9
        sb = np.abs(np.fft.rfft(b[s:s + win] * np.hanning(win))) + 1e-9
        peak = max(sa.max(), sb.max())
        mask = np.maximum(sa, sb) > peak * 1e-3  # -60 dB gate
        if mask.sum() == 0:
            continue
        dists.append(float(np.mean(np.abs(20 * np.log10(sa[mask] / sb[mask])))))
    dist = float(np.mean(dists)) if dists else 0.0
    if dist < 1.0:
        return {"level": "B", "bit_exact": False, "distance_db": round(dist, 3)}
    return {"level": None, "bit_exact": False,
            "distance_db": round(dist, 3),
            "note": "does not meet Level B; do not claim reproducibility"}
