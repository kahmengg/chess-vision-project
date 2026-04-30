# Chess Screen Overlay — Setup & Usage

A modular Python desktop application that:
1. **Connects** to Chrome's DevTools Protocol (CDP) to read the chess.com board DOM directly
2. **Converts** the live board state to a FEN string
3. **Queries** a local Stockfish engine for the top moves with smart tactical filtering
4. **Displays** coloured arrows and annotations on a transparent click-through overlay

---

## Installation

### 1. Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Stockfish binary

Download from **https://stockfishchess.org/download/**

- **Windows**: Place `stockfish-windows-x86-64-avx2.exe` in the project root.
- **Linux/macOS**: Place the `stockfish` binary in the project root, then:
  ```bash
  chmod +x stockfish
  ```

Alternatively, set `stockfish_path` in `config.py` to an absolute path.

---

## Project Structure

```
chess_overlay/
├── main.py            # Entry point & analysis loop
├── config.py          # All tunable settings in one place
├── vision.py          # Vision backend (Chrome CDP → FEN)
├── engine.py          # Stockfish UCI integration + smart filtering
├── overlay_ui.py      # Transparent click-through PyQt6 overlay
├── board_selector.py  # Auto-detect or click-drag board region
├── requirements.txt
└── README.md
```

---

## Running

### Step 1 — Open Chrome and go to chess.com
Start or join a game. The app will auto-connect to your Chrome tab.

> If Chrome is not already open, the app launches an isolated debug Chrome
> profile automatically and opens chess.com for you.

### Step 2 — Run the app

```bash
python main.py
```

### Step 3 — Board region
The app attempts to **auto-detect** the board position from the page.
If auto-detect fails, a full-screen dim overlay appears — **click and drag**
a rectangle around the chess board and release.

### Step 4 — Play
Move suggestions appear automatically as arrows on the overlay.
Press **Q** or click **✕ Quit Overlay** in the control panel to exit.

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `stockfish_path` | `stockfish-windows-x86-64-avx2.exe` | Path to Stockfish binary |
| `depth` | `15` | Analysis depth (higher = stronger/slower) |
| `num_moves` | `4` | Number of top moves to fetch from Stockfish |
| `refresh_interval_seconds` | `1.5` | Seconds between analysis cycles |
| `active_color` | `"auto"` | Side override: `"auto"` \| `"white"` \| `"black"` |
| `smart_mode` | `True` | Only show moves on critical tactical moments |
| `winning_threshold` | `200` | Suppress hints when you're ahead by this many centipawns |
| `critical_gap` | `80` | Show hint only when best move is this much better than 2nd best |

---

## Smart Mode

When **Smart Mode** is on (default), the overlay only suggests moves when there is a genuine tactical reason:

| Trigger | Example reason shown |
|---|---|
| Forced mate sequence | `⚠ Mate in 3 for you` |
| Piece under attack | `⚠ Queen under attack!` |
| Hanging piece | `⚠ Hanging Rook!` |
| Only move (large gap) | `⚡ Critical! Only move (gap +1.2)` |
| You're clearly winning | Suppressed — `You're winning (+2.5) — play freely ✓` |
| Even position, many good moves | Suppressed — `Many safe moves — play freely ✓` |

Toggle Smart Mode on/off anytime from the control panel without restarting.

---

## Overlay Controls

The control panel (top-left of screen) has:

- **🧠 Smart Mode** — toggle tactical filtering on/off
- **Side** — cycle between `Auto` / `White` / `Black` to override whose turn it is
- **✕ Quit Overlay** — exit the app (or press **Q**)

---

## Overlay Colour Key

| Colour | Meaning |
|---|---|
| 🟢 Green | Best move |
| 🔵 Blue | 2nd best |
| 🟡 Yellow | 3rd best |
| 🟠 Orange | 4th best |
| 🟣 Purple | 5th best |

Each arrow shows the SAN move name and eval score (e.g. `Nf3 +0.45`).
The **destination square** is highlighted with a semi-transparent tint and border
so the piece underneath remains visible.

---

## Architecture: Why the Loop Doesn't Max Out CPU

```
Background thread (daemon)
  └─ while True:
       1. vision.screenshot_to_fen()   # reads chess.com DOM via CDP (~10 ms)
       2. engine.get_smart_moves()     # Stockfish analysis (~200–1000 ms at depth 15)
       3. emit signal → Qt main thread # updates overlay
       4. stop_event.wait(1.5)         # BLOCKS for 1.5 s — zero CPU
```

`threading.Event.wait(timeout)` releases the GIL and sleeps the OS thread.
If the position hasn't changed, analysis is skipped entirely and the last
result is reused — no redundant Stockfish calls.

---

## How Vision Works (No Screen Capture Needed)

Unlike traditional overlays that take screenshots and run image recognition,
this app reads the board **directly from the chess.com page HTML** via Chrome's
DevTools Protocol (CDP):

- Piece positions are encoded as CSS classes on DOM elements (e.g. `piece wp square-45`)
- The app connects to Chrome's debug port (`localhost:9222`) and runs a small
  JavaScript snippet to extract all piece/square pairs
- This is faster, more accurate, and works at any screen resolution or zoom level
- No Selenium or special Chrome launch flags required for normal use —
  the app opens its own isolated debug Chrome profile if needed

---

## ⚠️ Fair Play Notice

This tool is designed for:
- Analysing **your own past games** for study and review
- Training against **computer bots** in local engines
- **Learning and improvement** in non-competitive contexts

Using real-time engine assistance during **rated online games** violates the
Terms of Service of every major chess platform (chess.com, Lichess, Chess24 etc.)
and is considered cheating. Please use responsibly.
