"""
overlay_ui.py — Transparent Chess Move Overlay
"""
from __future__ import annotations
from typing import List, Tuple
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QWidget, QApplication, QPushButton,
                              QLabel, QVBoxLayout)
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
    # Emits (moves, fen, debug, suppressed, reason)
    update_moves_signal = pyqtSignal(list, str, dict, bool, str)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._moves = []
        self._suppressed = False
        self._reason = ""
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
            QLabel#status_free  { color: #88ddaa; font-size: 11px; padding: 4px 12px; }
            QLabel#status_alert { color: #ffdd55; font-size: 11px; padding: 4px 12px; }
            QLabel#status_mate  { color: #ff5555; font-size: 11px; padding: 4px 12px; }
            QPushButton {
                background: #2a2a2a; color: #ccc; font-size: 11px;
                border: 1px solid #444; border-radius: 4px; padding: 4px 8px;
                margin: 2px 10px;
            }
            QPushButton:hover { background: #3a3a3a; }
            QPushButton:checked { background: #1a3a1a; border-color: #44aa44; color: #aaffaa; }
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
        layout.setSpacing(2)

        self._label = QLabel("♟  Chess Overlay\nAnalysing...")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        # Smart mode status line
        self._status_label = QLabel("")
        self._status_label.setObjectName("status_free")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Smart mode toggle button
        self._smart_btn = QPushButton("🧠  Smart Mode: ON")
        self._smart_btn.setCheckable(True)
        self._smart_btn.setChecked(getattr(self.config, "smart_mode", True))
        self._smart_btn.clicked.connect(self._toggle_smart_mode)
        layout.addWidget(self._smart_btn)

        # Side toggle
        self._side_btn = QPushButton(
            f"Side: {getattr(self.config, 'active_color', 'auto').title()}"
        )
        self._side_btn.clicked.connect(self._cycle_side)
        layout.addWidget(self._side_btn)

        quit_btn = QPushButton("✕  Quit Overlay")
        quit_btn.setObjectName("quit")
        quit_btn.clicked.connect(QApplication.quit)
        layout.addWidget(quit_btn)

        self._panel.adjustSize()
        self._panel.move(20, 20)

    def _setup_shortcuts(self):
        self._quit_shortcut = QShortcut(QKeySequence("Q"), self)
        self._quit_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._quit_shortcut.activated.connect(QApplication.quit)

    def _toggle_smart_mode(self, checked: bool):
        self.config.smart_mode = checked
        self._smart_btn.setText(f"🧠  Smart Mode: {'ON' if checked else 'OFF'}")

    def _cycle_side(self):
        current = getattr(self.config, "active_color", "auto")
        next_mode = {"auto": "white", "white": "black", "black": "auto"}.get(current, "auto")
        self.config.active_color = next_mode
        self._side_btn.setText(f"Side: {next_mode.title()}")

    def _board_flipped(self) -> bool:
        mode = getattr(self.config, "active_color", "auto")
        return mode == "black"

    def show(self):
        super().show()
        self._panel.show()

    def _on_update(self, moves, fen, debug, suppressed, reason):
        self._moves = moves
        self._suppressed = suppressed
        self._reason = reason
        self._last_debug = debug or {}

        if self.config.board_rect:
            l, t, r, b = self.config.board_rect
            region = f"Scan: ({l},{t}) -> ({r},{b})"
        else:
            region = "Scan: board not selected"

        active_mode = getattr(self.config, "active_color", "auto")
        status    = self._last_debug.get("status", "-")
        raw_nodes = self._last_debug.get("raw_nodes", 0)
        placed    = self._last_debug.get("placed", 0)
        message   = self._last_debug.get("message", "")
        board_side = "flipped" if self._board_flipped() else "white-side"
        debug_line = (
            f"Vision: {status} | nodes={raw_nodes} | "
            f"pieces={placed} | side={active_mode} | board={board_side}"
        )

        if moves:
            move_labels = ["🟢 Best", "🔵 2nd ", "🟡 3rd ", "🟠 4th ", "🟣 5th "]
            lines = []
            for i, m in enumerate(moves[:5]):
                prefix = move_labels[i] if i < len(move_labels) else f"  #{m.rank}"
                lines.append(f"{prefix}:  {m.san:6}  {m.score_display}")
            lines += ["", region, debug_line, message]
            self._label.setText("\n".join(lines))

            # Status label — alert or mate colour
            if "Mate" in reason or "mate" in reason:
                self._status_label.setObjectName("status_mate")
            else:
                self._status_label.setObjectName("status_alert")
            self._status_label.setText(reason)

        elif suppressed:
            self._label.setText(
                f"♟  Chess Overlay\n{region}\n{debug_line}\n{message}"
            )
            self._status_label.setObjectName("status_free")
            self._status_label.setText(reason)
        else:
            self._label.setText(
                f"♟  Waiting for readable position...\n"
                f"{region}\n{debug_line}\n{message}"
            )
            self._status_label.setText("")

        # Force style refresh after objectName change
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

        self.update()

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event):
        if not self.config.board_rect:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        left, top, right, bottom = self.config.board_rect
        cw = (right - left) / 8
        ch = (bottom - top) / 8

        # ── Scan-region border + grid ──────────────────────────────────────
        painter.setPen(QPen(QColor(70, 180, 255, 210), 3, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            int(left), int(top), int(right - left), int(bottom - top), 8, 8
        )
        painter.setPen(QPen(QColor(70, 180, 255, 120), 1))
        for i in range(1, 8):
            x = int(left + i * cw)
            y = int(top  + i * ch)
            painter.drawLine(x, int(top),  x, int(bottom))
            painter.drawLine(int(left), y, int(right),  y)

        if not self._moves:
            painter.end()
            return

        # ── Move colours ──────────────────────────────────────────────────
        color_defs = [
            getattr(self.config, "color_best",   (100, 220, 100, 200)),
            getattr(self.config, "color_second",  (100, 180, 255, 170)),
            getattr(self.config, "color_third",   (255, 200,  80, 150)),
            getattr(self.config, "color_fourth",  (255, 120,  80, 130)),
            getattr(self.config, "color_fifth",   (200,  80, 255, 120)),
        ]
        move_labels = ["Best", "2nd", "3rd", "4th", "5th"]
        flipped = self._board_flipped()

        for i, move in enumerate(self._moves[:5]):
            color = QColor(*color_defs[i])
            label_text = move_labels[i] if i < len(move_labels) else f"#{move.rank}"

            fc, fr = sq_screen(move.from_square, flipped)
            tc, tr = sq_screen(move.to_square,   flipped)
            fx = int(left + fc * cw)
            fy = int(top  + fr * ch)
            tx = int(left + tc * cw)
            ty = int(top  + tr * ch)

            # From square — dashed outline
            painter.setPen(QPen(color.lighter(170), 3, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(fx + 3, fy + 3, int(cw) - 6, int(ch) - 6, 4, 4)

            # Arrow shaft
            painter.setPen(QPen(color, 4))
            painter.drawLine(
                fx + int(cw / 2), fy + int(ch / 2),
                tx + int(cw / 2), ty + int(ch / 2),
            )

            # To square — filled block
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(tx + 1, ty + 1, int(cw) - 2, int(ch) - 2, 6, 6)

            # Label — shadow then highlight
            label = f"{label_text}: {move.san}\n{move.score_display}"
            painter.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
            painter.setPen(QColor(0, 0, 0, 210))
            painter.drawText(
                QRect(tx + 3, ty + 3, int(cw), int(ch)),
                Qt.AlignmentFlag.AlignCenter, label,
            )
            painter.setPen(QColor(255, 255, 255, 240))
            painter.drawText(
                QRect(tx + 1, ty + 1, int(cw), int(ch)),
                Qt.AlignmentFlag.AlignCenter, label,
            )

        painter.end()