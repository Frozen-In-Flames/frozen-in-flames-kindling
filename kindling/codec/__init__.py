"""Audio representation (Build Manual Part 5).

A compressed representation that can be generated efficiently without losing
what musicians care about. This version ships the real interface, the full
evaluation harness (a codec MUST be evaluated on its own before any generator
is built on it), and a deterministic reference codec in two rates: draft
(8-bit mu-law, 2:1) and high-fidelity (16-bit PCM, lossless). Frames are
independently decodable, so editing gets local reconstruction. Learned neural
codecs plug into the same interface later.
"""

from kindling.codec.codec import FramedCodec, decode_tokens, encode_audio
from kindling.codec.eval import evaluate_codec

__all__ = ["FramedCodec", "decode_tokens", "encode_audio", "evaluate_codec"]
