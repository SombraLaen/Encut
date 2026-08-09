"""Audio/video segment detection — three modes: silence, speech, video_use."""

import math
import re
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from segments import Segment, _merge_close_segments

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")
TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


@dataclass
class VideoUseTranscriptData:
    path: Path
    words: list
    phrases: list


def _hidden_subprocess_options() -> dict:
    import os
    if os.name != "nt":
        return {}
    options: dict = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "STARTUPINFO") and hasattr(subprocess, "STARTF_USESHOWWINDOW"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        options["startupinfo"] = startupinfo
    return options


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **_hidden_subprocess_options(), **kwargs)


def _popen(cmd: list[str], **kwargs) -> subprocess.Popen:
    return subprocess.Popen(cmd, **_hidden_subprocess_options(), **kwargs)


def _audio_mix_filter(audio_stream_count: int, output_label: str, tail_filter: Optional[str] = None) -> str:
    inputs = "".join(f"[0:a:{index}]" for index in range(audio_stream_count))
    filters = [
        f"{inputs}amix=inputs={audio_stream_count}:duration=longest:normalize=0",
        "alimiter=limit=0.95",
    ]
    if tail_filter:
        filters.append(tail_filter)
    return ",".join(filters) + f"[{output_label}]"


def _speech_filter_chain(sample_rate: int) -> str:
    return (
        "highpass=f=90,"
        "lowpass=f=7500,"
        f"aresample={sample_rate},"
        "aformat=sample_fmts=s16:channel_layouts=mono"
    )


def _pcm16le_rms_db(frame: bytes) -> float:
    sample_count = len(frame) // 2
    if sample_count == 0:
        return -120.0

    if HAS_NUMPY and sample_count > 64:
        arr = np.frombuffer(frame, dtype="<i2", count=sample_count)
        rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))
    else:
        fmt = f"<{sample_count}h"
        samples = struct.unpack(fmt, frame[: sample_count * 2])
        total = sum(s * s for s in samples)
        rms = math.sqrt(total / sample_count)

    if rms <= 0:
        return -120.0
    return 20 * math.log10(rms / 32768.0)


def _append_speech_segment(segments: list, start: float, end: float, min_keep: float) -> None:
    segment = Segment(max(0.0, start), max(0.0, end))
    if segment.duration >= min_keep:
        segments.append(segment)


def detect_silences(options, audio_stream_count: int, duration: float,
                    log: Callable[[str], None] = lambda _: None) -> tuple:
    log("Analisando audio para encontrar silencios...")
    cmd = [options.ffmpeg_path, "-hide_banner", "-nostdin", "-i", str(options.input_path)]
    if audio_stream_count > 1:
        cmd += [
            "-filter_complex",
            _audio_mix_filter(audio_stream_count, "detectaudio",
                              f"silencedetect=noise={options.threshold_db}dB:d={options.min_silence}"),
            "-map", "[detectaudio]",
        ]
    else:
        cmd += ["-af", f"silencedetect=noise={options.threshold_db}dB:d={options.min_silence}"]
    cmd += ["-f", "null", "-"]

    proc = _popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, universal_newlines=True)

    silences: list[Segment] = []
    current_start: Optional[float] = None
    started_at = time.monotonic()
    last_progress_log = 0.0
    assert proc.stderr is not None

    for line in proc.stderr:
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            current_start = float(start_match.group(1))
            continue
        end_match = SILENCE_END_RE.search(line)
        if end_match and current_start is not None:
            silences.append(Segment(current_start, float(end_match.group(1))))
            current_start = None
        time_match = TIME_RE.search(line)
        if duration and time_match:
            seen = _time_match_to_seconds(time_match)
            percent = min(100.0, seen / duration * 100)
            now = time.monotonic()
            if now - last_progress_log >= 2 or percent >= 100:
                from formatting import progress_line
                log(progress_line("Analisando", percent, now - started_at))
                last_progress_log = now

    code = proc.wait()
    if code != 0:
        raise RuntimeError("O ffmpeg falhou durante a deteccao de silencio.")
    if current_start is not None and duration:
        silences.append(Segment(current_start, duration))
    if not duration:
        duration = silences[-1].end if silences else 0.0
    return silences, duration


def detect_speech_segments(options, audio_stream_count: int, duration: float,
                          log: Callable[[str], None] = lambda _: None) -> tuple:
    import time
    log("Analisando fala com detector de voz...")
    sample_rate = 16000
    frame_ms = 20
    frame_bytes = int(sample_rate * frame_ms / 1000) * 2
    start_threshold = options.threshold_db
    end_threshold = options.threshold_db - 6.0

    cmd = [options.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(options.input_path)]
    speech_filter = _speech_filter_chain(sample_rate)
    if audio_stream_count > 1:
        cmd += [
            "-filter_complex",
            _audio_mix_filter(audio_stream_count, "speechaudio", speech_filter),
            "-map", "[speechaudio]",
        ]
    else:
        cmd += ["-map", "0:a:0?", "-af", speech_filter]
    cmd += ["-vn", "-f", "s16le", "-"]

    proc = _popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    assert proc.stdout is not None
    segments: list[Segment] = []
    current_start: Optional[float] = None
    last_voice_end: Optional[float] = None
    processed_frames = 0
    buffer = b""
    started_at = time.monotonic()
    last_progress_log = 0.0
    read_chunk_size = frame_bytes * 64

    if HAS_NUMPY:
        while True:
            chunk = proc.stdout.read(read_chunk_size)
            if not chunk:
                break
            buffer += chunk
            usable = len(buffer) // frame_bytes * frame_bytes
            frames_data = buffer[:usable]
            buffer = buffer[usable:]

            arr = np.frombuffer(frames_data, dtype="<i2")
            squared = arr.astype(np.float64) ** 2
            frame_count = len(arr)
            rms_values = 20.0 * np.log10(np.sqrt(np.maximum(np.mean(squared.reshape(-1, frame_bytes // 2), axis=1), 1e-12)) / 32768.0)

            for i in range(frame_count):
                frame_start = processed_frames * frame_ms / 1000
                frame_end = frame_start + frame_ms / 1000
                processed_frames += 1

                db = float(rms_values[i])
                threshold = end_threshold if current_start is not None else start_threshold
                has_voice = db >= threshold
                if has_voice:
                    if current_start is None:
                        current_start = frame_start
                    last_voice_end = frame_end
                elif current_start is not None and last_voice_end is not None:
                    if frame_end - last_voice_end >= options.min_silence:
                        _append_speech_segment(segments, current_start, last_voice_end, options.min_keep)
                        current_start = None
                        last_voice_end = None

            if duration:
                now = time.monotonic()
                if now - last_progress_log >= 2:
                    frame_end = processed_frames * frame_ms / 1000
                    percent = min(100.0, frame_end / duration * 100)
                    from formatting import progress_line
                    log(progress_line("Analisando fala", percent, now - started_at))
                    last_progress_log = now
    else:
        while True:
            chunk = proc.stdout.read(read_chunk_size)
            if not chunk:
                break
            buffer += chunk
            usable = len(buffer) // frame_bytes * frame_bytes
            frames_data = buffer[:usable]
            buffer = buffer[usable:]

            for offset in range(0, len(frames_data), frame_bytes):
                frame = frames_data[offset : offset + frame_bytes]
                frame_start = processed_frames * frame_ms / 1000
                frame_end = frame_start + frame_ms / 1000
                processed_frames += 1

                db = _pcm16le_rms_db(frame)
                threshold = end_threshold if current_start is not None else start_threshold
                has_voice = db >= threshold
                if has_voice:
                    if current_start is None:
                        current_start = frame_start
                    last_voice_end = frame_end
                elif current_start is not None and last_voice_end is not None:
                    if frame_end - last_voice_end >= options.min_silence:
                        _append_speech_segment(segments, current_start, last_voice_end, options.min_keep)
                        current_start = None
                        last_voice_end = None

            if duration:
                now = time.monotonic()
                if now - last_progress_log >= 2:
                    frame_end = processed_frames * frame_ms / 1000
                    percent = min(100.0, frame_end / duration * 100)
                    from formatting import progress_line
                    log(progress_line("Analisando fala", percent, now - started_at))
                    last_progress_log = now

    code = proc.wait()
    stderr = b""
    if proc.stderr is not None:
        stderr = proc.stderr.read() or b""
    if code != 0:
        tail = stderr.decode("utf-8", errors="replace").splitlines()[-8:]
        detail = "\n".join(tail).strip()
        raise RuntimeError("O ffmpeg falhou durante a deteccao de fala." + (f"\n{detail}" if detail else ""))

    detected_duration = processed_frames * frame_ms / 1000
    if current_start is not None and last_voice_end is not None:
        _append_speech_segment(segments, current_start, last_voice_end, options.min_keep)
    if not duration:
        duration = detected_duration
    if duration:
        from formatting import progress_line
        log(progress_line("Analisando fala", 100.0, time.monotonic() - started_at))
    return _merge_close_segments(segments, gap=0.03), duration


def _time_match_to_seconds(match: re.Match) -> float:
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
