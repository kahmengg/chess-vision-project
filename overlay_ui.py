"""
overlay_ui.py — Transparent Chess Move Overlay
"""
from __future__ import annotations
from typing import List, Tuple
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QWidget, QApplication, QPushButton,
                              QLabel, QVBoxLayout, QHBoxLayout)
from config import Config

FILES = "abcdefgh"
RANKS = "87654321"


def sq(name: str, flipped: bool = False) -> Tuple[int, int]:
    return FILES.index(name[0]), RANKS.index(name[1])


def sq_screen(name: str, flipped: bool = False) -> Tuple[int, int]:
    file_idx, rank_idx = sq(name, flipped)
    if flipped:
        return 7 - file_idx, 7 - rank_idx
    return file_idx, rank_idx


class ChessOverlayWindow(QWidget):
    update_moves_signal = pyqtSignal(list, str, dict)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._moves = []
        self._last_debug = {}
        self._quit_shortcut = None
        self._setup_overlay()
        self._setup_panel()
        self._setup_shortcuts()
        self.update_moves_signal.connect(self._on_update)

    def _setup_overlay(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(QApplication.primaryScreen().geometry())

    def _setup_panel(self):
        self._panel = QWidget()
        self._panel.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self._panel.setStyleSheet("""
            QWidget { background: rgba(15,15,15,225); border-radius: 10px; }
            QLabel  { color: #aaffaa; font-size: 12px;
                      padding: 8px 12px 2px 12px; }
            QPushButton {
                background: #2a2a2a; color: #ccc; font-size: 11px;
                border: 1px solid #444; border-radius: 4px; padding: 4px 8px;
            }
            QPushButton:hover { background: #3a3a3a; }
            #quit {
                background: #7a1a1a; color: white; font-weight: bold;
                font-size: 12px; border-color: #aa2222;
                padding: 6px; margin: 4px 10px 10px 10px;
            }
            #quit:hover { background: #aa2222; }
        """)
        self._panel.setFixedWidth(300)

        layout = QVBoxLayout(self._panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._label = QLabel("♟  Chess Overlay\nAnalysing...")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        self._side_btn = QPushButton("Side: Auto")
        self._side_btn.clicked.connect(self._cycle_side)
        self._side_btn.setText(
            f"Side: {getattr(self.config, 'active_color', 'auto').title()}"
        )
        layout.addWidget(self._side_btn)

        quit_btn = QPushButton("✕  Quit Overlay")
        quit_btn.setObjectName("quit")
        quit_btn.clicked.connect(QApplication.quit)
        layout.addWidget(quit_btn)

        self._panel.adjustSize()
        self._panel.move(20, 20)

    def _setup_shortcuts(self):
        # ApplicationShortcut works across all windows in this app.
        self._quit_shortcut = QShortcut(QKeySequence("Q"), self)
        self._quit_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._quit_shortcut.activated.connect(QApplication.quit)

    def _cycle_side(self):
        current = getattr(self.config, "active_color", "auto")
        next_mode = {
            "auto": "white",
            "white": "black",
            "black": "auto",
        }.get(current, "auto")
        self.config.active_color = next_mode
        self._side_btn.setText(f"Side: {next_mode.title()}")

    def _board_flipped(self) -> bool:
        mode = getattr(self.config, "active_color", "auto")
        if mode == "black":
            return True
        if mode == "white":
            return False
        return False

    def show(self):
        super().show()
        self._panel.show()

    def _on_update(self, moves, fen, debug):
        self._moves = moves
        self._last_debug = debug or {}
        if self.config.board_rect:
            l, t, r, b = self.config.board_rect
            region = f"Scan: ({l},{t}) -> ({r},{b})"
        else:
            region = "Scan: board not selected"

        active_mode = getattr(self.config, "active_color", "auto")

        status = self._last_debug.get("status", "-")
        raw_nodes = self._last_debug.get("raw_nodes", 0)
        placed = self._last_debug.get("placed", 0)
        message = self._last_debug.get("message", "")
        debug_line = f"Vision: {status} | nodes={raw_nodes} | pieces={placed} | side={active_mode}"

        if moves:
            top = moves[0]
            self._label.setText(
                f"♟  Best move: {top.san}  {top.score_display}\n"
                f"{region}\n{debug_line} | board={'flipped' if self._board_flipped() else 'white-side'}\n{message}"
            )
        else:
            self._label.setText(
                f"♟  Waiting for readable position...\n"
                f"{region}\n{debug_line} | board={'flipped' if self._board_flipped() else 'white-side'}\n{message}"
            )
        self.update()

    def paintEvent(self, event):
        if not self.config.board_rect:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        left, top, right, bottom = self.config.board_rect
        cw = (right - left) / 8
        ch = (bottom - top) / 8

        # Always show the active scan area and 8x8 grid for visibility.
        painter.setPen(QPen(QColor(70, 180, 255, 210), 3, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(int(left), int(top), int(right - left), int(bottom - top), 8, 8)

        painter.setPen(QPen(QColor(70, 180, 255, 120), 1))
        for i in range(1, 8):
            x = int(left + i * cw)
            y = int(top + i * ch)
            painter.drawLine(x, int(top), x, int(bottom))
            painter.drawLine(int(left), y, int(right), y)

        if not self._moves:
            painter.end()
            return

        if not self._moves:
            painter.end()
            return

        move = self._moves[0]
        color = QColor(*self.config.color_best)
        flipped = self._board_flipped()
        fc, fr = sq_screen(move.from_square, flipped)
        tc, tr = sq_screen(move.to_square, flipped)
        fx, fy = int(left + fc * cw), int(top + fr * ch)
        tx, ty = int(left + tc * cw), int(top + tr * ch)

        # From square — dotted outline
        painter.setPen(QPen(color.lighter(170), 3,
                            Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(fx+3, fy+3, int(cw)-6, int(ch)-6, 4, 4)

        # Arrow line
        painter.setPen(QPen(color, 4))
        painter.drawLine(fx+int(cw/2), fy+int(ch/2),
                         tx+int(cw/2), ty+int(ch/2))

        # To square — filled
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(tx+1, ty+1, int(cw)-2, int(ch)-2, 6, 6)

        # Label
        label = f"Best: {move.san}\n{move.score_display}"
        painter.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        painter.setPen(QColor(0, 0, 0, 210))
        painter.drawText(QRect(tx+3, ty+3, int(cw), int(ch)),
                         Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(QColor(255, 255, 255, 240))
        painter.drawText(QRect(tx+1, ty+1, int(cw), int(ch)),
                         Qt.AlignmentFlag.AlignCenter, label)
        painter.end()