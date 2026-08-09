"""Pure segment arithmetic — no I/O, no subprocesses, fully testable."""

from dataclasses import dataclass
from typing import Iterable


@dataclass
class Segment:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def build_keep_segments(
    silences: Iterable[Segment],
    duration: float,
    padding: float,
    min_keep: float,
) -> list[Segment]:
    keep: list[Segment] = []
    cursor = 0.0
    for silence in silences:
        start = max(0.0, silence.start - padding)
        end = min(duration, silence.end + padding)
        if start > cursor:
            segment = Segment(cursor, start)
            if segment.duration >= min_keep:
                keep.append(segment)
        cursor = max(cursor, end)
    if duration > cursor:
        segment = Segment(cursor, duration)
        if segment.duration >= min_keep:
            keep.append(segment)
    return _merge_close_segments(keep, gap=0.03)


def build_keep_segments_from_speech(
    speech_segments: Iterable[Segment],
    duration: float,
    padding: float,
    min_keep: float,
) -> list[Segment]:
    keep = []
    for segment in speech_segments:
        expanded = Segment(max(0.0, segment.start - padding), min(duration, segment.end + padding))
        if expanded.duration >= min_keep:
            keep.append(expanded)
    return _merge_close_segments(keep, gap=0.03)


def apply_protected_ranges(
    keep_segments: list[Segment],
    protected_ranges: list[Segment],
    duration: float,
) -> list[Segment]:
    if not protected_ranges:
        return keep_segments
    merged = list(keep_segments)
    for segment in protected_ranges:
        start = max(0.0, segment.start)
        end = min(duration, segment.end) if duration > 0 else segment.end
        if end > start:
            merged.append(Segment(start, end))
    return _merge_close_segments(sorted(merged, key=lambda s: s.start), gap=0.03)


def parse_ignore_ranges(text: str, duration: float = 0.0) -> list[Segment]:
    import re
    text = (text or "").strip()
    if not text:
        return []
    tokens = re.findall(r"\d+(?::\d{1,2}){0,2}(?:[\.,]\d+)?", text)
    if not tokens:
        raise ValueError("Informe os intervalos protegidos no formato 01:30-03:00.")
    if len(tokens) % 2:
        raise ValueError("Cada intervalo protegido precisa ter inicio e fim, por exemplo 01:30-03:00.")
    ranges = []
    for index in range(0, len(tokens), 2):
        start = _parse_time_value(tokens[index])
        end = _parse_time_value(tokens[index + 1])
        if end <= start:
            raise ValueError(f"Intervalo protegido invalido: {tokens[index]}-{tokens[index + 1]}.")
        if duration > 0:
            if start >= duration:
                continue
            end = min(end, duration)
        ranges.append(Segment(max(0.0, start), end))
    return _merge_close_segments(sorted(ranges, key=lambda s: s.start), gap=0.001)


def merge_close_segments(segments: list[Segment], gap: float = 0.03) -> list[Segment]:
    return _merge_close_segments(segments, gap)


def _merge_close_segments(segments: list[Segment], gap: float) -> list[Segment]:
    if not segments:
        return []
    merged = [segments[0]]
    for segment in segments[1:]:
        previous = merged[-1]
        if segment.start - previous.end <= gap:
            previous.end = max(previous.end, segment.end)
        else:
            merged.append(segment)
    return merged


def _parse_time_value(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"Tempo invalido: {value}")
