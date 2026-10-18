"""Apply a preset to new material (10.1, step 5)."""

import numpy as np

from .effects import apply_effect_chain


def render_preset(audio: np.ndarray, rate: int,
                  preset: dict) -> np.ndarray:
    """Render the preset's effect chain on audio (mono or stereo)."""
    stereo = np.asarray(audio, dtype=float)
    if stereo.ndim == 1:
        stereo = np.stack([stereo, stereo])
    return apply_effect_chain(stereo, rate, preset["chain"])
