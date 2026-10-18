# Audio representation (Part 5)

A compressed representation that can be generated efficiently without losing
what musicians care about.

## Reference codec

`kindling.codec.FramedCodec` implements the `AudioCodec` interface in two
honest rates behind one contract:

- **draft**: 8-bit mu-law companded frames, 2:1 smaller than 16-bit PCM.
  Fast previews. Genuinely lossy (about 32 dB SNR on the test battery) with
  graceful degradation.
- **hifi**: 16-bit PCM frames, lossless (about 83 dB SNR, quantization only).

Both keep stereo (channels interleaved per frame), both decode isolated
regions (frames are independent, so a frame-aligned region reconstructs
bit-exactly), and both support multi-track token sets so separate parts can
be generated and replaced independently (stem-aware latents).

This is the reference implementation that establishes the interface and the
evaluation harness. Learned neural codecs plug into the same interface; the
bake-off in V6 judges renderers through it, and any codec can be swapped
without touching the rest of the system.

## Evaluation

`kindling.codec.eval.evaluate_codec()` runs the objective acceptance
battery on five signal categories (drums, vocals, solo piano, dense mix,
quiet material):

- **Spectral error**: mean log-spectral distance in dB, floor 100 dB below
  peak, counting only bins within 60 dB of each frame's peak (differences
  buried deeper are inaudible under the frame's own content).
- **Transient preservation**: surviving onset flux near each original onset.
- **Stereo correlation**: per-channel plus L-R difference correlation, which
  carries the stereo image.
- **Loudness drift**: worst windowed RMS level difference, skipping windows
  below -60 dBFS where the metric would measure quantization noise against
  silence instead of the codec.
- **Seam energy**: max sample difference where a region decode meets the
  full decode. Frame-aligned regions must be bit-exact.

Thresholds live in `THRESHOLDS` in the eval module, per rate. Both rates
pass the full battery. The listening half of the acceptance tests follows
`docs/listening-protocol.md` and is run by human panels, not CI.
