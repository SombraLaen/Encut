"""Batch job builder — generate output paths from input lists."""

from pathlib import Path
from typing import Optional


def build_batch_jobs(input_paths: list, output_dir: Path, template, suffix: str = "_sem_silencio") -> list:
    output_dir = output_dir.expanduser()
    used_outputs: set = set()
    jobs = []
    for input_path in input_paths:
        output_path = _unique_batch_output(input_path, output_dir, suffix, used_outputs)
        jobs.append(_clone_options(template, input_path, output_path))
    return jobs


def _unique_batch_output(input_path: Path, output_dir: Path, suffix: str, used_outputs: set) -> Path:
    base_name = f"{input_path.stem}{suffix}.mp4"
    candidate = output_dir / base_name
    counter = 2
    while candidate in used_outputs or candidate.exists():
        candidate = output_dir / f"{input_path.stem}{suffix}_{counter}.mp4"
        counter += 1
    used_outputs.add(candidate)
    return candidate


def _clone_options(options, input_path: Path, output_path: Path):
    from dataclasses import replace
    return replace(options, input_path=input_path, output_path=output_path)
