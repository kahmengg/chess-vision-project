"""
config.py — All settings in one place.
"""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Config:
    # Local Stockfish executable in the project folder
    stockfish_path: str = "stockfish-windows-x86-64-avx2.exe"

    # How many seconds between each analysis
    refresh_interval_seconds: float = 1.0

    # Number of moves to show
    num_moves: int = 1

    # Stockfish depth via chess-api.com (max 18, default 12)
    depth: int = 12

    # Board region on screen — set when you drag the box
    board_rect: Optional[Tuple[int, int, int, int]] = None

    # Side to analyze: "auto", "white", or "black"
    active_color: str = "auto"

    # Overlay highlight colours (R, G, B, Alpha)
    color_best:   Tuple = (0,   220, 100, 180)
    color_second: Tuple = (255, 200,   0, 150)
    color_third:  Tuple = (220,  80,  80, 130)