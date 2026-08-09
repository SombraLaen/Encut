"""Encut C-compatible API DLL — exports video processing for any language."""

import ctypes
import sys
import os
from pathlib import Path

from silence_cutter import (
    CutterOptions,
    cut_video,
    parse_duration,
    count_audio_streams,
    default_ffmpeg_path,
    log_noop,
)

__all__ = [
    'get_version',
    'get_ffmpeg_path',
    'probe_video',
    'process_video',
]


def get_version() -> str:
    from silence_cutter import APP_VERSION
    return APP_VERSION


def get_ffmpeg_path() -> str:
    return default_ffmpeg_path()


def probe_video(video_path: str) -> dict:
    p = Path(video_path)
    if not p.exists():
        raise FileNotFoundError(f"Video not found: {p}")
    ffmpeg = default_ffmpeg_path()
    return {
        "path": str(p),
        "duration": parse_duration(ffmpeg, p),
        "audio_streams": count_audio_streams(ffmpeg, p),
    }


def process_video(
    input_path: str,
    output_path: str,
    threshold_db: float = -35.0,
    min_silence: float = 0.45,
    padding: float = 0.12,
    min_keep: float = 0.18,
    detection_mode: str = "speech",
    mode: str = "reencode",
    log_callback=None,
) -> dict:
    options = CutterOptions(
        input_path=Path(input_path),
        output_path=Path(output_path),
        ffmpeg_path=default_ffmpeg_path(),
        threshold_db=float(threshold_db),
        min_silence=float(min_silence),
        padding=float(padding),
        min_keep=float(min_keep),
        detection_mode=detection_mode,
        mode=mode,
    )
    log_fn = log_callback if log_callback else log_noop
    return cut_video(options, log=log_fn)
