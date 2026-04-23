"""
Chess Screen Overlay — Main
============================================================
SETUP (one time):
    1. pip install -r requirements.txt

EVERY TIME YOU PLAY:
    1. Go to chess.com and start or join a game
    2. Run: python main.py
    3. Done — highlights appear automatically (or drag-select fallback)
    4. Press Q (or click "Quit Overlay") to exit
"""

import sys
import threading

import chess
from PyQt6.QtWidgets import QApplication

from board_selector import BoardSelectorWindow
from overlay_ui import ChessOverlayWindow
from vision import VisionModule
from engine import ChessEngine
from config import Config


def main():
    app = QApplication(sys.argv)
    config = Config()

    print("[Main] Connecting to local Stockfish...")
    engine = ChessEngine(config)

    print("[Main] Connecting to Chrome / chess.com...")
    try:
        vision = VisionModule(config)
    except Exception as e:
        print(e)
        print("Fix: Open Chrome and chess.com (or let the app launch it), then run main.py again.")
        sys.exit(1)

    overlay = ChessOverlayWindow(config)
    selector = BoardSelectorWindow(config, vision=vision)

    def on_board_selected(rect):
        print(f"[Main] Board region: {rect}")
        config.board_rect = rect
        overlay.show()
        _start_loop(overlay, vision, engine, config)

    selector.board_selected.connect(on_board_selected)
    selector.show()

    sys.exit(app.exec())


def _start_loop(overlay, vision, engine, config):
    stop = threading.Event()
    empty_board_fen = "8/8/8/8/8/8/8/8"
    failed_reads = 0
    last_fen = None
    last_moves = []

    def worker():
        nonlocal failed_reads, last_fen, last_moves
        while not stop.is_set():
            try:
                fen = vision.screenshot_to_fen()
                debug = vision.get_last_debug()

                if fen:
                    print(f"[Main] FEN: {fen}")

                    analysis_fen = fen
                    active_mode = getattr(config, "active_color", "auto")
                    if active_mode != "auto":
                        board = chess.Board(fen)
                        board.turn = (active_mode == "white")
                        analysis_fen = board.fen()
                        if analysis_fen != fen:
                            print(f"[Main] Side override applied: {active_mode}")

                    board_flipped = (active_mode == "black")
                    if board_flipped != getattr(config, "board_flipped", False):
                        config.board_flipped = board_flipped

                    if analysis_fen.split(" ")[0] == empty_board_fen:
                        print("[Main] Empty board detected — skipping analysis.")
                        failed_reads += 1
                        overlay.update_moves_signal.emit([], analysis_fen, debug)
                        stop.wait(timeout=config.refresh_interval_seconds)
                        continue

                    if analysis_fen == last_fen:
                        print("[Main] Position unchanged — reusing last analysis.")
                        overlay.update_moves_signal.emit(last_moves, analysis_fen, debug)
                        stop.wait(timeout=config.refresh_interval_seconds)
                        continue

                    failed_reads = 0
                    moves = engine.get_top_moves(analysis_fen)
                    if moves:
                        last_fen = analysis_fen
                        last_moves = moves
                        for m in moves:
                            print(f"  #{m.rank}  {m.san:8} {m.score_display}")
                        overlay.update_moves_signal.emit(moves, analysis_fen, debug)
                    else:
                        print("[Main] No moves — game over or position unreadable.")
                        overlay.update_moves_signal.emit([], analysis_fen, debug)
                        if getattr(engine, "last_call_had_restart", False):
                            print("[Main] Stockfish restarted, will rescan this position on next cycle.")
                            last_fen = None
                            last_moves = []
                        else:
                            last_fen = analysis_fen
                            last_moves = []
                else:
                    print("[Main] Could not read board from page.")
                    failed_reads += 1
                    overlay.update_moves_signal.emit([], "", debug)

                if failed_reads >= 3:
                    rect = vision.get_board_rect_from_page()
                    if rect and (rect[2] - rect[0]) > 100:
                        if config.board_rect != rect:
                            print(f"[Main] Auto-updated scan region to {rect}")
                            config.board_rect = rect
                    failed_reads = 0
            except Exception as e:
                import traceback
                traceback.print_exc()

            stop.wait(timeout=config.refresh_interval_seconds)

    threading.Thread(target=worker, daemon=True).start()
    return stop


if __name__ == "__main__":
    main()