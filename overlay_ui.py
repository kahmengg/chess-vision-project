"""
overlay_ui.py — Transparent Chess Move Overlay
"""
from __future__ import annotations
import math
from typing import List, Tuple
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import (QPainter, QColor, QFont, QPen, QBrush,
                          QKeySequence, QShortcut, QPolygon, QRegion)
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


def _arrowhead_polygon(x1: int, y1: int, x2: int, y2: int,
                        size: int = 16) -> QPolygon:
    """Return a filled triangle polygon for the arrow tip at (x2, y2)."""
    angle = math.atan2(y2 - y1, x2 - x1)
    spread = math.radians(28)
    p1 = QPoint(
        int(x2 - size * math.cos(angle - spread)),
        int(y2 - size * math.sin(angle - spread)),
    )
    p2 = QPoint(
        int(x2 - size * math.cos(angle + spread)),
        int(y2 - size * math.sin(angle + spread)),
    )
    return QPolygon([QPoint(x2, y2), p1, p2])


class ChessOverlayWindow(QWidget):
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

        # Windows: set WS_EX_TRANSPARENT so the OS-level hit-test
        # also ignores this window, guaranteeing clicks pass through.
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE    = -20
            WS_EX_LAYERED  = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
        except Exception:
            pass  # Non-Windows or ctypes unavailable — WA_TransparentForMouseEvents still applies

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

        self._status_label = QLabel("")
        self._status_label.setObjectName("status_free")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._smart_btn = QPushButton("🧠  Smart Mode: ON")
        self._smart_btn.setCheckable(True)
        self._smart_btn.setChecked(getattr(self.config, "smart_mode", True))
        self._smart_btn.clicked.connect(self._toggle_smart_mode)
        layout.addWidget(self._smart_btn)

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
        return getattr(self.config, "active_color", "auto") == "black"

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

        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

        # Re-punch the click-through hole whenever the board rect might change
        self._update_mask()
        self.update()

    def _update_mask(self):
        """
        Cut a fully transparent (click-through) hole over the board area.
        Everything outside the board still belongs to the overlay window
        but passes through via WA_TransparentForMouseEvents.
        Setting an empty/null mask on the whole widget achieves the same —
        the WS_EX_TRANSPARENT flag (Windows) handles it at the OS level.
        We just clear any leftover mask so Qt doesn't accidentally block input.
        """
        self.clearMask()

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
        painter.setPen(QPen(QColor(70, 180, 255, 60), 1))
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
        flipped = self._board_flipped()

        for i, move in enumerate(self._moves[:5]):
            color = QColor(*color_defs[i])

            fc, fr = sq_screen(move.from_square, flipped)
            tc, tr = sq_screen(move.to_square,   flipped)
            fx = int(left + fc * cw)
            fy = int(top  + fr * ch)
            tx = int(left + tc * cw)
            ty = int(top  + tr * ch)

            # Centre points
            fcx = fx + int(cw / 2)
            fcy = fy + int(ch / 2)
            tcx = tx + int(cw / 2)
            tcy = ty + int(ch / 2)

            # ── From square — dashed outline only, no fill ─────────────────
            painter.setPen(QPen(color.lighter(170), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(fx + 4, fy + 4, int(cw) - 8, int(ch) - 8, 4, 4)

            # ── Arrow shaft — stop short of destination centre ─────────────
            # Shorten endpoint so shaft doesn't overlap arrowhead
            shaft_shorten = 14
            angle = math.atan2(tcy - fcy, tcx - fcx)
            ex = int(tcx - shaft_shorten * math.cos(angle))
            ey = int(tcy - shaft_shorten * math.sin(angle))

            painter.setPen(QPen(color, 5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(fcx, fcy, ex, ey)

            # ── Arrowhead ─────────────────────────────────────────────────
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawPolygon(_arrowhead_polygon(fcx, fcy, tcx, tcy, size=15))

            # ── To square — thin border + very light tint ──────────────────
            fill_color = QColor(color.red(), color.green(), color.blue(), 45)
            painter.setPen(QPen(color.lighter(150), 2))
            painter.setBrush(QBrush(fill_color))
            painter.drawRoundedRect(tx + 3, ty + 3, int(cw) - 6, int(ch) - 6, 5, 5)

            # ── Label (SAN + score) ────────────────────────────────────────
            label = f"{move.san}\n{move.score_display}"
            painter.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            # Shadow
            painter.setPen(QColor(0, 0, 0, 180))
            painter.drawText(
                QRect(tx + 3, ty + 3, int(cw), int(ch)),
                Qt.AlignmentFlag.AlignCenter, label,
            )
            # Highlight
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawText(
                QRect(tx + 1, ty + 1, int(cw), int(ch)),
                Qt.AlignmentFlag.AlignCenter, label,
            )

        painter.end()