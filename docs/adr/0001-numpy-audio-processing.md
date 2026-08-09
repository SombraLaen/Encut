# ADR 0001: Use numpy for vectorized audio RMS calculation

## Status

Accepted

## Context

The original `_pcm16le_rms_db` function computed RMS energy for audio frames using a pure-Python loop — iterating over every 2-byte sample in a frame, squaring, summing, then taking the square root. For a typical 20ms frame at 16kHz, this meant 160 iterations per frame, millions of times over a long video.

The speech detection path (`detect_speech_segments`) calls this function for every frame of audio, making it the single hottest function in the codebase during analysis.

## Decision

Use numpy for vectorized RMS calculation when available, with a `struct.unpack` fallback when numpy is not installed.

```python
if HAS_NUMPY and sample_count > 64:
    arr = np.frombuffer(frame, dtype="<i2", count=sample_count)
    rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))
else:
    samples = struct.unpack(fmt, frame[: sample_count * 2])
    total = sum(s * s for s in samples)
    rms = math.sqrt(total / sample_count)
```

The detection loop also has a numpy-fast path that processes entire chunks at once using reshaped arrays and vectorized dB conversion.

## Consequences

- **Positive:** 10-50x speedup in frame-level RMS calculation for long videos
- **Positive:** numpy is already a common dependency in Python audio/video tooling
- **Negative:** numpy becomes an optional dependency (graceful degradation handles absence)
- **Negative:** Two code paths to maintain (numpy and fallback)
