"""Pure formatting utilities — no side effects, no dependencies."""

import math


def format_seconds(value: float) -> str:
    value = max(0.0, value)
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"


def format_duration(value: float) -> str:
    if value <= 0:
        return "duracao desconhecida"
    return format_seconds(value)


def format_bytes(size: int) -> str:
    value = float(abs(size))
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    sign = "-" if size < 0 else ""
    if unit == "B":
        return f"{sign}{int(value)} {unit}"
    return f"{sign}{value:.2f} {unit}"


def format_percent(value: float, total: float) -> str:
    if total <= 0:
        return "percentual indisponivel"
    return f"{value / total * 100:.1f}%"


def format_size_delta(reduced_size: int, original_size: int) -> str:
    if reduced_size >= 0:
        return f"reduzido {format_bytes(reduced_size)} ({format_percent(reduced_size, original_size)})"
    return f"aumentou {format_bytes(abs(reduced_size))} ({format_percent(abs(reduced_size), original_size)})"


def progress_line(label: str, percent: float, elapsed: float) -> str:
    return (
        f"{label}: {percent:5.1f}% | "
        f"decorrido {format_seconds(elapsed)} | "
        f"estimado restante {format_eta(elapsed, percent)}"
    )


def format_eta(elapsed: float, percent: float) -> str:
    if percent <= 0:
        return "calculando"
    remaining = elapsed * (100 - percent) / percent
    return format_seconds(remaining)


def percent_number(value: float, total: float):
    if total <= 0:
        return None
    return round(value / total * 100, 3)


def format_optional_percent(value) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1f}%"
    return "indisponivel"
