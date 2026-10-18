"""Audio loading for the asset library (Phase A).

WAV is read with the stdlib wave module (PCM 8/16/24/32-bit and 32-bit
float). Anything else (MP3 and friends) is decoded with ffmpeg when it is
available. Everything lands as float32 in [-1, 1] at the target rate, mono
or stereo on request. No new Python dependencies.
"""

from __future__ import annotations

import hashlib
import os
import struct
import subprocess
import tempfile
import wave
from typing import Tuple

import numpy as np


def _resample_linear(x: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or len(x) == 0:
        return x.astype(np.float32)
    ratio = dst_rate / src_rate
    n_out = max(1, int(len(x) * ratio))
    idx = np.linspace(0, len(x) - 1, n_out)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


def _read_wav_pcm(path: str) -> Tuple[np.ndarray, int]:
    """Raw PCM/float WAV via stdlib. Returns (samples, rate); samples are
    float32 shaped (channels, n)."""
    with wave.open(path, "rb") as w:
        n_ch = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        n_frames = w.getnframes()
        raw = w.readframes(n_frames)
    if width == 1:
        ints = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        data = (ints - 128.0) / 128.0
    elif width == 2:
        ints = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        data = ints / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        ints = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8)
                | (b[:, 2].astype(np.int32) << 16))
        ints = np.where(ints >= 0x800000, ints - 0x1000000, ints).astype(np.float32)
        data = ints / 8388608.0
    elif width == 4:
        # Could be 32-bit int or 32-bit float; wave does not say. Try int
        # first; if the values look like float32 bit patterns in [-1, 1],
        # reinterpret. Heuristic: int32 PCM of real audio has large
        # magnitudes; float32 audio sits in [-1, 1].
        as_int = np.frombuffer(raw, dtype=np.int32).astype(np.float64)
        if np.max(np.abs(as_int)) > 2 ** 24:
            data = (as_int / 2147483648.0).astype(np.float32)
        else:
            as_float = np.frombuffer(raw, dtype=np.float32)
            if np.max(np.abs(as_float)) <= 1.5:
                data = as_float
            else:
                data = (as_int / 2147483648.0).astype(np.float32)
    else:
        raise ValueError(f"unsupported sample width {width}")
    data = data.reshape(-1, n_ch).T
    return data.astype(np.float32), rate


def _decode_ffmpeg(path: str, target_rate: int) -> Tuple[np.ndarray, int]:
    """Decode any ffmpeg-readable format to stereo float32 at target_rate."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", path,
             "-ac", "2", "-ar", str(target_rate),
             "-f", "f32le", "-acodec", "pcm_f32le", tmp_path],
            check=True)
        raw = open(tmp_path, "rb").read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    data = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T
    return data, target_rate


def load_audio(path: str, target_rate: int = 44100,
               mono: bool = True,
               max_seconds: float = None) -> Tuple[np.ndarray, int]:
    """Load an audio file. Returns (samples, target_rate).

    samples: float32, shape (n,) if mono else (2, n). Raises a clear error
    for unreadable files instead of guessing.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"audio file not found: {path}")
    suffix = os.path.splitext(path)[1].lower()
    data = None
    if suffix == ".wav":
        try:
            data, rate = _read_wav_pcm(path)
        except (wave.Error, EOFError, struct.error):
            data = None
    if data is None:
        try:
            data, rate = _decode_ffmpeg(path, target_rate)
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            raise ValueError(
                f"could not decode {path!r} as WAV and ffmpeg is "
                f"unavailable or failed: {e}")
    if max_seconds is not None:
        keep = int(max_seconds * rate)
        data = data[:, :keep]
    if rate != target_rate:
        data = np.stack([_resample_linear(ch, rate, target_rate)
                         for ch in data])
        rate = target_rate
    if mono and data.shape[0] == 2:
        data = data.mean(axis=0)
    elif not mono and data.shape[0] == 1:
        data = np.stack([data[0], data[0]])
    return data.astype(np.float32), rate


def audio_sha256(samples: np.ndarray, rate: int) -> str:
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(samples).tobytes())
    h.update(str(rate).encode())
    return h.hexdigest()[:32]
