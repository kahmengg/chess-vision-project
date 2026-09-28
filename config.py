"""
config.py - Central configuration for Chess Overlay.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional, Tuple


LOGGER = logging.getLogger(__name__)
CONFIG_FILE = Path(__file__).with_name("config.local.json")


@dataclass
class Config:
    # Stockfish
    stockfish_path: str = "stockfish-windows-x86-64-avx2.exe"
    depth: int = 15
    num_moves: int = 4
    analysis_time_seconds: float = 0.35
    analysis_cache_size: int = 128

    # Smart mode
    smart_mode: bool = True
    winning_threshold: int = 200
    critical_gap: int = 80

    # Vision / scanning
    board_rect: Optional[Tuple[int, int, int, int]] = None
    refresh_interval_seconds: float = 0.5

    # Side override
    active_color: str = "auto"       # "auto" | "white" | "black"
    board_flipped: bool = False

    # Safety
    study_mode: bool = True
    allow_live_assistance: bool = False

    # Overlay colours (R, G, B, A)
    color_best: Tuple[int, int, int, int] = field(default_factory=lambda: (100, 220, 100, 200))
    color_second: Tuple[int, int, int, int] = field(default_factory=lambda: (100, 180, 255, 170))
    color_third: Tuple[int, int, int, int] = field(default_factory=lambda: (255, 200, 80, 150))
    color_fourth: Tuple[int, int, int, int] = field(default_factory=lambda: (255, 120, 80, 130))
    color_fifth: Tuple[int, int, int, int] = field(default_factory=lambda: (200, 80, 255, 120))


def load_config(path: Path = CONFIG_FILE) -> Config:
    """Load optional local JSON overrides without requiring users to edit source."""
    config = Config()
    if not path.exists():
        return config

    allowed = {item.name for item in fields(Config)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.warning("Could not read %s: %s", path, exc)
        return config

    for key, value in data.items():
        if key not in allowed:
            LOGGER.warning("Ignoring unknown config key: %s", key)
            continue
        if key.startswith("color_") and isinstance(value, list):
            value = tuple(value)
        setattr(config, key, value)

    return config
