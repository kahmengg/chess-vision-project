# Chess Screen Overlay - Setup & Usage

A Python desktop overlay that reads a chess.com board through Chrome DevTools,
converts it to FEN, asks a local Stockfish engine for candidate moves, and paints
arrows on a transparent PyQt overlay.

This project is designed for study, bot games, and post-game review. Real-time
engine assistance is disabled by default on likely live chess.com pages.

## Installation

```bash
pip install -r requirements.txt
```

Download Stockfish from https://stockfishchess.org/download/ and either:

- put `stockfish-windows-x86-64-avx2.exe` in the project root on Windows
- put `stockfish` in the project root on Linux/macOS and run `chmod +x stockfish`
- copy `config.local.example.json` to `config.local.json` and set an absolute `stockfish_path`

## Running

```bash
python main.py
```

The app launches or connects to a Chrome instance with remote debugging, finds a
chess.com tab, detects the board, and then starts the overlay. If board detection
fails, drag a square around the board.

## Configuration

Default settings live in `config.py`. For local changes, create
`config.local.json`; it is read automatically and keeps your personal settings
out of source code.

Useful settings:

| Setting | Default | Purpose |
|---|---:|---|
| `stockfish_path` | `stockfish-windows-x86-64-avx2.exe` | Local engine binary |
| `depth` | `15` | Strength ceiling for Stockfish |
| `analysis_time_seconds` | `0.35` | Time budget per new position |
| `analysis_cache_size` | `128` | Number of analyzed positions to cache |
| `num_moves` | `4` | Candidate moves requested from Stockfish |
| `refresh_interval_seconds` | `0.5` | DOM read cadence |
| `smart_mode` | `true` | Show hints only in tactical moments |
| `study_mode` | `true` | Prefer learning/review behavior |
| `allow_live_assistance` | `false` | Keep live-game hints disabled |

## Current Architecture

```text
main.py
  starts Qt, Stockfish, Chrome/CDP, board selection, and the worker loop

vision.py
  reads chess.com DOM through Chrome DevTools and returns FEN/debug state

engine.py
  wraps Stockfish, caches repeated analyses, applies hint policy, returns mate PVs

overlay_ui.py
  paints arrows and status text only; it does not call Stockfish directly

board_selector.py
  auto-detects the board or lets the user drag-select it
```

## Fair Play Notice

Use this for:

- reviewing your own completed games
- training against bots or local engines
- learning tactics and candidate moves in non-competitive contexts

Do not use real-time engine help in rated or competitive online games. By
default, the app suppresses engine hints on likely live chess.com pages.
