"""
Chess Screen Overlay - Main entry point.
"""
from __future__ import annotations

import logging
import sys
import threading

import chess
from PyQt6.QtWidgets import QApplication

from board_selector import BoardSelectorWindow
from config import load_config
from engine import ChessEngine
from overlay_ui import ChessOverlayWindow
from vision import VisionModule


LOGGER = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    app = QApplication(sys.argv)
    config = load_config()

    LOGGER.info("Connecting to local Stockfish")
    engine = ChessEngine(config)

    LOGGER.info("Connecting to Chrome / chess.com")
    try:
        vision = VisionModule(config)
    except Exception as exc:
        LOGGER.error("%s", exc)
        LOGGER.error("Fix: open Chrome and chess.com, or let the app launch it, then run main.py again.")
        sys.exit(1)

    overlay = ChessOverlayWindow(config, engine=engine)
    selector = BoardSelectorWindow(config, vision=vision)

    def on_board_selected(rect):
        LOGGER.info("Board region: %s", rect)
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
    last_result = None
    last_smart_mode = getattr(config, "smart_mode", True)

    def worker():
        nonlocal failed_reads, last_fen, last_result, last_smart_mode

        while not stop.is_set():
            try:
                fen = vision.screenshot_to_fen()
                debug = vision.get_last_debug()

                if fen:
                    LOGGER.info("FEN: %s", fen)
                    analysis_fen = fen
                    active_mode = getattr(config, "active_color", "auto")

                    # Vision reads these independently: turn controls analysis,
                    # while orientation controls where arrows are painted.
                    detected_flipped = debug.get("board_flipped")
                    if detected_flipped is not None:
                        config.board_flipped = bool(detected_flipped)
                    detected_rect = debug.get("board_rect")
                    if (
                        detected_rect
                        and detected_rect[2] - detected_rect[0] > 100
                        and detected_rect[3] - detected_rect[1] > 100
                    ):
                        config.board_rect = tuple(detected_rect)

                    if active_mode != "auto":
                        board = chess.Board(fen)
                        board.turn = active_mode == "white"
                        analysis_fen = board.fen()
                        if analysis_fen != fen:
                            LOGGER.info("Side override applied: %s", active_mode)

                    if analysis_fen.split(" ")[0] == empty_board_fen:
                        failed_reads += 1
                        overlay.update_moves_signal.emit([], analysis_fen, debug, False, "Empty board", [])
                        stop.wait(timeout=config.refresh_interval_seconds)
                        continue

                    if _live_assistance_blocked(debug, config):
                        reason = "Study mode: live game detected - engine hints disabled"
                        last_fen = analysis_fen
                        last_result = None
                        overlay.update_moves_signal.emit([], analysis_fen, debug, True, reason, [])
                        stop.wait(timeout=config.refresh_interval_seconds)
                        continue

                    current_smart_mode = getattr(config, "smart_mode", True)
                    if (
                        analysis_fen == last_fen
                        and last_result is not None
                        and current_smart_mode == last_smart_mode
                    ):
                        LOGGER.info("Position unchanged - reusing last analysis")
                        overlay.update_moves_signal.emit(
                            last_result.moves,
                            analysis_fen,
                            debug,
                            last_result.suppressed,
                            last_result.reason,
                            last_result.mate_sequence,
                        )
                        stop.wait(timeout=config.refresh_interval_seconds)
                        continue

                    last_smart_mode = current_smart_mode
                    failed_reads = 0

                    result = engine.get_smart_moves(analysis_fen)
                    last_fen = analysis_fen
                    last_result = result

                    if result.moves:
                        LOGGER.info("%s", result.reason)
                        for move in result.moves:
                            LOGGER.info("  #%s %s %s", move.rank, f"{move.san:8}", move.score_display)
                    else:
                        LOGGER.info("Suppressed: %s", result.reason)

                    overlay.update_moves_signal.emit(
                        result.moves,
                        analysis_fen,
                        debug,
                        result.suppressed,
                        result.reason,
                        result.mate_sequence,
                    )

                    if getattr(engine, "last_call_had_restart", False):
                        LOGGER.info("Stockfish restarted - will rescan on next cycle")
                        last_fen = None
                        last_result = None

                else:
                    LOGGER.info("Could not read board from page")
                    failed_reads += 1
                    overlay.update_moves_signal.emit([], "", debug, False, "", [])

                if failed_reads >= 3:
                    rect = vision.get_board_rect_from_page()
                    if rect and (rect[2] - rect[0]) > 100 and config.board_rect != rect:
                        LOGGER.info("Auto-updated scan region to %s", rect)
                        config.board_rect = rect
                    failed_reads = 0

            except Exception:
                LOGGER.exception("Worker loop error")

            stop.wait(timeout=config.refresh_interval_seconds)

    threading.Thread(target=worker, daemon=True).start()
    return stop


def _live_assistance_blocked(debug, config) -> bool:
    """Keep real-time help off on likely live competitive chess.com pages."""
    if getattr(config, "allow_live_assistance", False):
        return False
    if not getattr(config, "study_mode", True):
        return False

    url = (debug or {}).get("url", "").lower()
    if "chess.com" not in url:
        return False

    training_hints = (
        "/analysis",
        "/game/computer",
        "/play/computer",
        "/bot",
        "/lessons",
        "/puzzles",
    )
    if any(hint in url for hint in training_hints):
        return False

    live_hints = ("/game/live", "/play/online", "/live", "/play")
    return any(hint in url for hint in live_hints)


if __name__ == "__main__":
    main()
