"""Preset management — JSON persistence for user settings."""

import json
from pathlib import Path
from typing import Optional

PRESETS_FILENAME = "presets_ajustes.json"
UI_PREFERENCES_FILENAME = "preferencias_ui.json"


def presets_path(base_dir: Path) -> Path:
    return base_dir / PRESETS_FILENAME


def ui_preferences_path(base_dir: Path) -> Path:
    return base_dir / UI_PREFERENCES_FILENAME


def default_presets() -> dict:
    return {
        "Padrao": {
            "threshold_db": -35.0,
            "min_silence": 0.45,
            "padding": 0.12,
            "min_keep": 0.18,
            "detection_mode": "speech",
            "mode": "reencode",
        }
    }


def normalize_preset(values: dict) -> dict:
    try:
        mode = str(values.get("mode", "reencode"))
        if mode not in {"reencode", "copy"}:
            mode = "reencode"
        detection_mode = str(values.get("detection_mode", "speech"))
        if detection_mode not in {"speech", "silence", "video_use"}:
            detection_mode = "speech"
        return {
            "threshold_db": float(values.get("threshold_db", -35.0)),
            "min_silence": float(values.get("min_silence", 0.45)),
            "padding": float(values.get("padding", 0.12)),
            "min_keep": float(values.get("min_keep", 0.18)),
            "detection_mode": detection_mode,
            "mode": mode,
        }
    except (TypeError, ValueError):
        return {}


def load_presets(path: Optional[Path] = None, base_dir: Optional[Path] = None) -> dict:
    p = path or presets_path(base_dir or Path.cwd())
    if not p.exists():
        return default_presets()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_presets()
    raw = data.get("presets") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return default_presets()
    presets = {}
    for name, values in raw.items():
        if isinstance(name, str) and isinstance(values, dict):
            normalized = normalize_preset(values)
            if normalized:
                presets[name] = normalized
    return presets


def save_presets(presets: dict, path: Optional[Path] = None, base_dir: Optional[Path] = None) -> None:
    p = path or presets_path(base_dir or Path.cwd())
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "updated_at": _now_iso(), "presets": presets}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_ui_preferences(path: Optional[Path] = None, base_dir: Optional[Path] = None) -> dict:
    p = path or ui_preferences_path(base_dir or Path.cwd())
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_ui_preferences(preferences: dict, path: Optional[Path] = None, base_dir: Optional[Path] = None) -> None:
    p = path or ui_preferences_path(base_dir or Path.cwd())
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "updated_at": _now_iso(), "dark_mode": bool(preferences.get("dark_mode", False))}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
