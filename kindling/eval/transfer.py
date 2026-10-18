"""Transfer tests (17.4): capabilities beyond the input that created them.

- Voice character recognizable on new lyrics/melodies?
- Inferred preset works on a different song/instrumentation?
- Distilled instrument performs new passages?
- One asset changes while others stay stable?
- Edits predictable across sections and full renders?
"""

from typing import Any, Dict

import numpy as np


def transfer_voice_new_lyrics(identity_vec_a, identity_vec_b) -> Dict:
    """Same character, new lyrics: identity must hold."""
    from kindling.assets.voice import identity_similarity
    sim = identity_similarity(identity_vec_a, identity_vec_b)
    return {"passed": sim > 0.7, "similarity": round(sim, 3),
            "test": "voice_new_lyrics"}


def transfer_preset_new_song(preset: Dict, ref_features: Dict,
                             new_features: Dict) -> Dict:
    """Preset applied to a different song: character captured?

    Compares the direction of change, not absolute values.
    """
    # Both should move the same way relative to neutral.
    keys = ["crest_db", "stereo_correlation"]
    aligned = 0
    for k in keys:
        if k in ref_features and k in new_features:
            # Sign of (new - neutral) should match (ref - neutral).
            # Neutral baselines: crest 12, corr 0.8.
            neutral = {"crest_db": 12, "stereo_correlation": 0.8}[k]
            if (new_features[k] - neutral) * (ref_features[k] - neutral) > 0:
                aligned += 1
    return {"passed": aligned >= 1, "aligned_features": aligned,
            "test": "preset_new_song"}


def transfer_instrument_new_passages(student, teacher,
                                     passages, rate: int) -> Dict:
    """Distilled instrument on unseen passages (not training examples)."""
    from kindling.instruments.distill import _spectral_distance
    dists = []
    for notes, controls in passages:
        t = teacher.render(notes, controls, rate, seed=5)
        s = student.render(notes, controls, rate, seed=5)
        dists.append(_spectral_distance(t, s, rate))
    mean_d = float(np.mean(dists))
    return {"passed": mean_d < 6.0, "mean_distance_db": round(mean_d, 2),
            "test": "instrument_new_passages"}


def transfer_asset_stability(before: Dict[str, np.ndarray],
                             after: Dict[str, np.ndarray],
                             changed_asset: str) -> Dict:
    """One asset changes; others stay stable (perceptually)."""
    from kindling.editing.locality import perceptual_distance
    stable = True
    detail = {}
    for name, audio in before.items():
        if name == changed_asset or name not in after:
            continue
        d = perceptual_distance(audio, after[name], 22050)
        detail[name] = round(d, 2)
        if d > 1.0:
            stable = False
    return {"passed": stable, "detail": detail,
            "test": "asset_stability"}
