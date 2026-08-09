"""FFmpeg probe — video metadata extraction with internal caching."""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from formatting import format_bytes


_ffprobe_cache: dict[str, tuple[float, int, float]] = {}


def _cache_key(ffmpeg_path: str, input_path: Path) -> str:
    try:
        stat = input_path.stat()
        return f"{ffmpeg_path}|{input_path}|{stat.st_size}|{stat.st_mtime}"
    except OSError:
        return f"{ffmpeg_path}|{input_path}"


def _cache_put(key: str, duration: float) -> None:
    _ffprobe_cache[key] = (duration, 0, time.monotonic())
    if len(_ffprobe_cache) > 32:
        oldest_key = min(_ffprobe_cache, key=lambda k: _ffprobe_cache[k][2])
        del _ffprobe_cache[oldest_key]


def _cache_update_streams(key: str, stream_count: int) -> None:
    cached = _ffprobe_cache.get(key)
    if cached is not None:
        _ffprobe_cache[key] = (cached[0], stream_count, cached[2])
    else:
        _ffprobe_cache[key] = (0.0, stream_count, time.monotonic())


def clear_cache() -> None:
    _ffprobe_cache.clear()


def _hidden_subprocess_options() -> dict:
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


def _guess_ffprobe_path(ffmpeg_path: str) -> Optional[str]:
    ffmpeg = Path(ffmpeg_path)
    if ffmpeg.name.lower() in {"ffmpeg.exe", "ffmpeg"} and ffmpeg.parent != Path("."):
        candidate = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffprobe")


def require_ffmpeg(ffmpeg_path: str) -> None:
    try:
        _run([ffmpeg_path, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "ffmpeg nao encontrado. Rode o instalador para baixar as dependencias ou informe o caminho do ffmpeg.exe."
        ) from exc


def parse_duration(ffmpeg_path: str, input_path: Path) -> float:
    key = _cache_key(ffmpeg_path, input_path)
    cached = _ffprobe_cache.get(key)
    if cached is not None:
        return cached[0]

    ffprobe_path = _guess_ffprobe_path(ffmpeg_path)
    if ffprobe_path:
        cmd = [
            ffprobe_path, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        proc = _run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            duration = float((proc.stdout or "").strip())
            if duration > 0:
                _cache_put(key, duration)
                return duration
        except ValueError:
            pass

    cmd = [ffmpeg_path, "-hide_banner", "-i", str(input_path)]
    proc = _run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    text = proc.stderr or ""
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    _cache_put(key, duration)
    return duration


def count_audio_streams(ffmpeg_path: str, input_path: Path) -> int:
    key = _cache_key(ffmpeg_path, input_path)
    cached = _ffprobe_cache.get(key)
    if cached is not None and cached[1] > 0:
        return cached[1]

    ffprobe_path = _guess_ffprobe_path(ffmpeg_path)
    if ffprobe_path:
        cmd = [
            ffprobe_path, "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(input_path),
        ]
        proc = _run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if proc.returncode == 0:
            count = len([line for line in (proc.stdout or "").splitlines() if line.strip()])
            _cache_update_streams(key, count)
            return count

    cmd = [ffmpeg_path, "-hide_banner", "-i", str(input_path)]
    proc = _run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    count = sum(1 for line in (proc.stderr or "").splitlines() if "Stream #" in line and "Audio:" in line)
    _cache_update_streams(key, count)
    return count
