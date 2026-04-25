"""
config.py — Central configuration for Chess Overlay
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class Config:
    # ── Stockfish ──────────────────────────────────────────────────────────
    stockfish_path: str = "stockfish-windows-x86-64-avx2.exe"
    depth: int = 15
    num_moves: int = 5               # how many moves to fetch from Stockfish internally

    # ── Smart mode ────────────────────────────────────────────────────────
    # When True, only shows a move on critical "only move" tactical moments.
    # When False, shows top moves every turn (old behaviour).
    smart_mode: bool = True

    # Suppress suggestion when your eval advantage exceeds this (centipawns).
    # 250 = +2.5 pawns. You're clearly better — play freely.
    winning_threshold: int = 200

    # Only show a suggestion when the gap between move #1 and move #2
    # exceeds this (centipawns). 150 = only show "forced" / brilliant moves.
    # Lower = more suggestions. Higher = only show on very critical moments.
    critical_gap: int = 80

    # ── Vision / scanning ─────────────────────────────────────────────────
    board_rect: Optional[Tuple[int, int, int, int]] = None
    refresh_interval_seconds: float = 1.5

    # ── Side override ──────────────────────────────────────────────────────
    active_color: str = "auto"       # "auto" | "white" | "black"
    board_flipped: bool = False

    # ── Overlay colours (R, G, B, A) ──────────────────────────────────────
    color_best:   Tuple[int, int, int, int] = field(default_factory=lambda: (100, 220, 100, 200))  # green
    color_second: Tuple[int, int, int, int] = field(default_factory=lambda: (100, 180, 255, 170))  # blue
    color_third:  Tuple[int, int, int, int] = field(default_factory=lambda: (255, 200,  80, 150))  # yellow
    color_fourth: Tuple[int, int, int, int] = field(default_factory=lambda: (255, 120,  80, 130))  # orange
    color_fifth:  Tuple[int, int, int, int] = field(default_factory=lambda: (200,  80, 255, 120))  # purple