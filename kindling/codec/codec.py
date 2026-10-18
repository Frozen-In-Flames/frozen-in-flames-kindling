"""Reference framed codec (Part 5).

Two honest rates behind one interface:
- "draft": 8-bit mu-law companded frames (G.711-style), 2:1 smaller than
  16-bit PCM, graceful quality loss. Fast previews.
- "hifi": 16-bit PCM frames, lossless. Full-quality rendering.

Both keep stereo (channels are interleaved per frame), both decode isolated
regions (frames are independent), and both support multi-track token sets so
separate parts can be generated and replaced (stem-aware latents).
"""

from __future__ import annotations

import base64
import math
from typing import Any, Dict, List, Optional

import numpy as np

from kindling.interfaces import AudioCodec as AudioCodecABC

FRAME_SIZE = 2048
MU = 255.0
RATES = ("draft", "hifi")


def _mulaw_encode(samples: np.ndarray) -> bytes:
    x = np.clip(samples, -1.0, 1.0)
    compressed = np.sign(x) * np.log1p(MU * np.abs(x)) / np.log1p(MU)
    return ((compressed * 127.5 + 127.5).astype(np.uint8)).tobytes()


def _mulaw_decode(raw: bytes, count: int) -> np.ndarray:
    codes = np.frombuffer(raw, dtype=np.uint8).astype(np.float64)[:count]
    y = (codes - 127.5) / 127.5
    return np.sign(y) * (np.expm1(np.abs(y) * np.log1p(MU))) / MU


def _pcm16_encode(samples: np.ndarray) -> bytes:
    x = np.clip(samples, -1.0, 1.0)
    return (np.round(x * 32767).astype(np.int16)).tobytes()


def _pcm16_decode(raw: bytes, count: int) -> np.ndarray:
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64)[:count] / 32767.0


def _as_stereo(samples: np.ndarray) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float64)
    if arr.ndim == 1:
        arr = np.stack([arr, arr], axis=1)
    return arr


class FramedCodec(AudioCodecABC):
    """Independently-decodable framed codec. The unit of tokens is one frame."""

    def __init__(self, rate: str = "hifi", frame_size: int = FRAME_SIZE):
        if rate not in RATES:
            raise ValueError(f"unknown rate {rate!r}")
        self.rate = rate
        self.frame_size = frame_size

    @property
    def component_name(self) -> str:
        return "Audio codec and latent space"

    @property
    def supported_tiers(self) -> List[str]:
        return ["draft", "studio", "hosted"]

    @property
    def compression_ratio(self) -> float:
        return 2.0 if self.rate == "draft" else 1.0

    def _encode_frame(self, frame: np.ndarray) -> str:
        flat = frame.reshape(-1)
        raw = _mulaw_encode(flat) if self.rate == "draft" else _pcm16_encode(flat)
        return base64.b64encode(raw).decode("ascii")

    def _decode_frame(self, token: str, channels: int) -> np.ndarray:
        raw = base64.b64decode(token.encode("ascii"))
        count = self.frame_size * channels
        flat = _mulaw_decode(raw, count) if self.rate == "draft" else _pcm16_decode(raw, count)
        return flat.reshape(self.frame_size, channels)

    def encode(self, audio: Dict[str, Any]) -> Dict[str, Any]:
        stereo = _as_stereo(audio["samples"])
        n = len(stereo)
        frames = []
        for start in range(0, n, self.frame_size):
            frame = np.zeros((self.frame_size, stereo.shape[1]))
            chunk = stereo[start:start + self.frame_size]
            frame[:len(chunk)] = chunk
            frames.append(self._encode_frame(frame))
        return {
            "codec": "kindling-framed",
            "codec_version": "5.0.0",
            "rate": self.rate,
            "sample_rate": audio.get("sample_rate", 48000),
            "channels": stereo.shape[1],
            "frame_size": self.frame_size,
            "total_samples": n,
            "frames": frames,
        }

    def decode(self, tokens: Dict[str, Any]) -> Dict[str, Any]:
        self._check(tokens)
        channels = tokens["channels"]
        out = np.zeros((tokens["total_samples"], channels))
        for i, token in enumerate(tokens["frames"]):
            frame = self._decode_frame(token, channels)
            start = i * self.frame_size
            end = min(start + self.frame_size, tokens["total_samples"])
            out[start:end] = frame[:end - start]
        return {"samples": out, "sample_rate": tokens["sample_rate"]}

    def decode_region(self, tokens: Dict[str, Any], start_s: float,
                      end_s: float) -> Dict[str, Any]:
        """Decode only the frames overlapping [start_s, end_s). Frame-aligned
        regions reconstruct exactly what full decode produces there."""
        self._check(tokens)
        sr = tokens["sample_rate"]
        first = max(0, int(start_s * sr) // self.frame_size)
        last = min(len(tokens["frames"]) - 1,
                   int(math.ceil(end_s * sr)) // self.frame_size)
        channels = tokens["channels"]
        frames = [self._decode_frame(tokens["frames"][i], channels)
                  for i in range(first, last + 1)]
        region = np.concatenate(frames, axis=0) if frames else np.zeros((0, channels))
        return {"samples": region, "sample_rate": sr,
                "region_start_sample": first * self.frame_size}

    def encode_multitrack(self, parts: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Stem-aware token set: one token stream per part plus the mix."""
        tracks = {name: self.encode(audio) for name, audio in parts.items()}
        return {"codec": "kindling-framed-multitrack",
                "codec_version": "5.0.0", "rate": self.rate,
                "tracks": tracks}

    def decode_multitrack(self, tokens: Dict[str, Any],
                          names: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        tracks = tokens["tracks"]
        wanted = names or list(tracks.keys())
        return {name: self.decode(tracks[name]) for name in wanted}

    def _check(self, tokens: Dict[str, Any]) -> None:
        if tokens.get("codec") != "kindling-framed":
            raise ValueError("not kindling framed tokens")
        if tokens.get("rate") != self.rate:
            raise ValueError(
                f"tokens are rate {tokens.get('rate')!r}, codec is {self.rate!r}")


def encode_audio(samples: np.ndarray, sample_rate: int = 48000,
                 rate: str = "hifi") -> Dict[str, Any]:
    return FramedCodec(rate=rate).encode({"samples": samples, "sample_rate": sample_rate})


def decode_tokens(tokens: Dict[str, Any]) -> Dict[str, Any]:
    return FramedCodec(rate=tokens["rate"]).decode(tokens)
