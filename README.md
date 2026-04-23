# Chess Screen Overlay — Setup & Usage

A modular Python desktop application that:
1. **Captures** a selected region of your screen (the chess board)
2. **Converts** the visual state to a FEN string via perceptual image hashing
3. **Queries** a local Stockfish engine for the top 3 suggested moves
4. **Displays** coloured highlights and annotations on a transparent overlay

---

## Installation

### 1. Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Stockfish binary

Download from **https://stockfishchess.org/download/**

- **Linux/macOS**: Place the `stockfish` binary in the project root, then:
  ```bash
  chmod +x stockfish
  ```
- **Windows**: Place `stockfish.exe` in the project root.

Alternatively, set `stockfish_path` in `config.py` to an absolute path.

---

## Project Structure

```
chess_overlay/
├── main.py            # Entry point & analysis loop
├── config.py          # All tunable settings in one place
├── vision.py          # Vision backend (screen capture → FEN)
├── engine.py          # Stockfish UCI integration
├── overlay_ui.py      # Transparent click-through PyQt6 overlay
├── board_selector.py  # Click-drag board region calibration
├── requirements.txt
└── README.md
```

---

## First-Run Calibration (Board Region Only)

### Step A: Board Region (automatic)
When you launch the app, a full-screen dim overlay appears.
**Click and drag** a rectangle around the chess board on your screen.
Release the mouse — the overlay window will now track that region.

## Running

```bash
python main.py
```

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `stockfish_path` | `./stockfish` | Path to Stockfish binary |
| `stockfish_depth` | `15` | Analysis depth (higher = stronger/slower) |
| `stockfish_multipv` | `3` | Number of top moves to fetch |
| `refresh_interval_seconds` | `3.0` | Seconds between analysis cycles |
| `active_color` | `"w"` | Whose turn: `"w"` or `"b"` |
| `overlay_opacity` | `0.85` | Overlay transparency (0=invisible, 1=opaque) |
| `vision_backend` | `"hash"` | Vision module: `"hash"` or your custom key |

---

## Swapping the Vision Module

The vision layer is abstracted behind `VisionModuleBase`.
To plug in a DOM scraper (e.g. for chess.com's live board):

```python
# my_dom_vision.py
from vision import VisionModuleBase

class DomVisionModule(VisionModuleBase):
    def capture(self, board_rect):
        return None  # Not needed for DOM scraping

    def screenshot_to_fen(self, screenshot):
        # Use Selenium/Playwright to read the board DOM
        # and return a FEN string
        ...
```

Then in `vision.py`, add to the `backends` dict:
```python
backends = {
    "hash": HashVisionModule,
    "dom":  DomVisionModule,   # ← add this
}
```

And in `config.py`:
```python
vision_backend: str = "dom"
```

---

## Architecture: Why the Loop Doesn't Max Out CPU

```
Background thread (daemon)
  └─ while True:
       1. capture()              # ~5–15 ms
       2. screenshot_to_fen()    # ~50–200 ms (hashing 64 cells)
       3. get_top_moves()        # ~200–1000 ms (Stockfish at depth 15)
       4. emit signal → Qt main thread
       5. stop_event.wait(3.0)   # BLOCKS for 3 seconds — zero CPU
```

`threading.Event.wait(timeout)` releases the GIL and sleeps the OS thread.
CPU usage between analysis cycles is effectively 0%.

---

## Overlay Colour Key

| Colour | Meaning |
|---|---|
| 🟢 Green | #1 best move |
| 🟡 Amber | #2 second-best |
| 🔴 Red | #3 third-best |

Each highlighted square shows: `#N SAN_move\nScore` (e.g. `#1 e4\n+0.35`)

---

## ⚠️ Fair Play Notice

This tool is designed for:
- Analysing **grandmaster games** from databases offline
- Training against **computer bots** in local engines
- **Study and learning** in non-competitive contexts

Using real-time engine assistance during **rated online games** violates the
Terms of Service of every major chess platform (chess.com, Lichess, Chess24, etc.)
and is considered cheating. Several platforms use transparency-layer detection
heuristics in their fair-play systems.
