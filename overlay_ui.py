"""
overlay_ui.py - Transparent chess move overlay.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QKeySequence, QPainter, QPen, QPolygon, QShortcut
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from config import Config


FILES = "abcdefgh"
RANKS = "87654321"


def sq(name: str) -> Tuple[int, int]:
    return FILES.index(name[0]), RANKS.index(name[1])


def sq_screen(name: str, flipped: bool = False) -> Tuple[int, int]:
    file_idx, rank_idx = sq(name)
    if flipped:
        return 7 - file_idx, 7 - rank_idx
    return file_idx, rank_idx


def _arrowhead_polygon(x1: int, y1: int, x2: int, y2: int, size: int = 16) -> QPolygon:
    angle = math.atan2(y2 - y1, x2 - x1)
    spread = math.radians(28)
    p1 = QPoint(int(x2 - size * math.cos(angle - spread)), int(y2 - size * math.sin(angle - spread)))
    p2 = QPoint(int(x2 - size * math.cos(angle + spread)), int(y2 - size * math.sin(angle + spread)))
    return QPolygon([QPoint(x2, y2), p1, p2])


class ChessOverlayWindow(QWidget):
    update_moves_signal = pyqtSignal(list, str, dict, bool, str, list)

    def __init__(self, config: Config, parent=None, engine=None):
        super().__init__(parent)
        self.config = config
        self.engine = engine
        self._moves = []
        self._suppressed = False
        self._reason = ""
        self._last_debug = {}
        self._mate_sequence: Optional[list[Tuple[str, str]]] = None
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
        # Cover the complete virtual desktop. A primary-screen-only overlay makes
        # otherwise-correct board coordinates drift or disappear on monitor 2.
        self.setGeometry(QApplication.primaryScreen().virtualGeometry())

        try:
            import ctypes
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00080000 | 0x00000020)
        except Exception:
            pass

    def _setup_panel(self):
        self._panel = QWidget()
        self._panel.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self._panel.setStyleSheet("""
            QWidget { background: rgba(15,15,15,225); border-radius: 10px; }
            QLabel  { color: #aaffaa; font-size: 12px; padding: 8px 12px 2px 12px; }
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

        self._label = QLabel("Chess Overlay\nAnalysing...")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        self._status_label = QLabel("")
        self._status_label.setObjectName("status_free")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._smart_btn = QPushButton("Smart Mode: ON")
        self._smart_btn.setCheckable(True)
        self._smart_btn.setChecked(getattr(self.config, "smart_mode", True))
        self._smart_btn.clicked.connect(self._toggle_smart_mode)
        layout.addWidget(self._smart_btn)

        self._side_btn = QPushButton(f"Side: {getattr(self.config, 'active_color', 'auto').title()}")
        self._side_btn.clicked.connect(self._cycle_side)
        layout.addWidget(self._side_btn)

        quit_btn = QPushButton("Quit Overlay")
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
        self._smart_btn.setText(f"Smart Mode: {'ON' if checked else 'OFF'}")

    def _cycle_side(self):
        current = getattr(self.config, "active_color", "auto")
        next_mode = {"auto": "white", "white": "black", "black": "auto"}.get(current, "auto")
        self.config.active_color = next_mode
        self._side_btn.setText(f"Side: {next_mode.title()}")

    def _board_flipped(self) -> bool:
        # Board orientation is a property of the page, not of whose turn we ask
        # Stockfish to analyse. Keeping these separate fixes arrows mirrored in
        # Auto mode and when the side-to-move override is used.
        return bool(getattr(self.config, "board_flipped", False))

    def show(self):
        super().show()
        self._panel.show()

    def _on_update(self, moves, fen, debug, suppressed, reason, mate_sequence):
        self._moves = moves
        self._suppressed = suppressed
        self._reason = reason
        self._last_debug = debug or {}
        is_mate = "mate" in reason.lower()
        self._mate_sequence = mate_sequence if is_mate and mate_sequence else None

        if self.config.board_rect:
            left, top, right, bottom = self.config.board_rect
            region = f"Scan: ({left},{top}) -> ({right},{bottom})"
        else:
            region = "Scan: board not selected"

        active_mode = getattr(self.config, "active_color", "auto")
        status = self._last_debug.get("status", "-")
        raw_nodes = self._last_debug.get("raw_nodes", 0)
        placed = self._last_debug.get("placed", 0)
        message = self._last_debug.get("message", "")
        page_url = self._last_debug.get("url", "")
        board_side = "flipped" if self._board_flipped() else "white-side"
        debug_line = f"Vision: {status} | nodes={raw_nodes} | pieces={placed} | side={active_mode} | board={board_side}"

        if moves:
            move_labels = ["Best", "2nd", "3rd", "4th", "5th"]
            lines = []

            if is_mate and self._mate_sequence:
                lines.append(f"Mate sequence ({len(self._mate_sequence)} moves):")
                for idx, (frm, to) in enumerate(self._mate_sequence):
                    who = "You" if idx % 2 == 0 else "Them"
                    lines.append(f"  {idx+1}. {who}: {frm}->{to}")
            else:
                for idx, move in enumerate(moves[:5]):
                    prefix = move_labels[idx] if idx < len(move_labels) else f"#{move.rank}"
                    lines.append(f"{prefix}: {move.san:6} {move.score_display}")

            if page_url:
                lines.append(f"Page: {page_url[:52]}")
            lines += ["", region, debug_line, message]
            self._label.setText("\n".join(lines))
            self._status_label.setObjectName("status_mate" if is_mate else "status_alert")
            self._status_label.setText(reason)

        elif suppressed:
            self._label.setText(f"Chess Overlay\n{region}\n{debug_line}\n{message}")
            self._status_label.setObjectName("status_free")
            self._status_label.setText(reason)
        else:
            self._label.setText(f"Waiting for readable position...\n{region}\n{debug_line}\n{message}")
            self._status_label.setText("")

        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        self.update()

    def _draw_arrow(
        self,
        painter,
        color,
        fcx,
        fcy,
        tcx,
        tcy,
        cw,
        ch,
        fx,
        fy,
        tx,
        ty,
        label: str,
        shaft_width: int = 5,
        arrow_size: int = 15,
        fill_alpha: int = 45,
        dash_from: bool = True,
    ):
        """Draw a single move arrow with a small label."""
        pen_style = Qt.PenStyle.DashLine if dash_from else Qt.PenStyle.SolidLine
        painter.setPen(QPen(color.lighter(170), 2, pen_style))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(fx + 4, fy + 4, int(cw) - 8, int(ch) - 8, 4, 4)

        angle = math.atan2(tcy - fcy, tcx - fcx)
        shorten = arrow_size - 1
        ex = int(tcx - shorten * math.cos(angle))
        ey = int(tcy - shorten * math.sin(angle))
        painter.setPen(QPen(color, shaft_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(fcx, fcy, ex, ey)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(_arrowhead_polygon(fcx, fcy, tcx, tcy, size=arrow_size))

        fill_color = QColor(color.red(), color.green(), color.blue(), fill_alpha)
        painter.setPen(QPen(color.lighter(150), 2))
        painter.setBrush(QBrush(fill_color))
        painter.drawRoundedRect(tx + 3, ty + 3, int(cw) - 6, int(ch) - 6, 5, 5)

        painter.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        painter.setPen(QColor(0, 0, 0, 180))
        painter.drawText(QRect(tx + 3, ty + 3, int(cw), int(ch)), Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(QColor(255, 255, 255, 230))
        painter.drawText(QRect(tx + 1, ty + 1, int(cw), int(ch)), Qt.AlignmentFlag.AlignCenter, label)

    def paintEvent(self, event):
        if not self.config.board_rect:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        left, top, right, bottom = self.config.board_rect
        # board_rect uses global desktop coordinates; QPainter uses coordinates
        # local to this overlay (important when the virtual desktop starts < 0).
        left -= self.geometry().left()
        right -= self.geometry().left()
        top -= self.geometry().top()
        bottom -= self.geometry().top()
        cw = (right - left) / 8
        ch = (bottom - top) / 8

        painter.setPen(QPen(QColor(70, 180, 255, 210), 3, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(int(left), int(top), int(right - left), int(bottom - top), 8, 8)
        painter.setPen(QPen(QColor(70, 180, 255, 60), 1))
        for idx in range(1, 8):
            x = int(left + idx * cw)
            y = int(top + idx * ch)
            painter.drawLine(x, int(top), x, int(bottom))
            painter.drawLine(int(left), y, int(right), y)

        if not self._moves:
            painter.end()
            return

        flipped = self._board_flipped()
        is_mate = "mate" in self._reason.lower()
        if is_mate and self._mate_sequence:
            your_colors = [
                QColor(80, 220, 80, 220),
                QColor(120, 220, 80, 190),
                QColor(160, 200, 80, 160),
                QColor(200, 180, 80, 140),
            ]
            their_color = QColor(220, 80, 80, 120)
            mate_for_you = "against" not in self._reason.lower()

            for idx, (frm, to) in enumerate(self._mate_sequence):
                your_turn = (idx % 2 == 0) if mate_for_you else (idx % 2 == 1)
                if your_turn:
                    color = your_colors[min(idx // 2, len(your_colors) - 1)]
                    alpha, shaft_w, arr_sz = 55, 5, 15
                else:
                    color = their_color
                    alpha, shaft_w, arr_sz = 30, 3, 10

                self._paint_move_arrow(painter, color, frm, to, flipped, left, top, cw, ch, f"{idx+1}\n{frm}->{to}", shaft_w, arr_sz, alpha, not your_turn)
            painter.end()
            return

        color_defs = [
            getattr(self.config, "color_best", (100, 220, 100, 200)),
            getattr(self.config, "color_second", (100, 180, 255, 170)),
            getattr(self.config, "color_third", (255, 200, 80, 150)),
            getattr(self.config, "color_fourth", (255, 120, 80, 130)),
            getattr(self.config, "color_fifth", (200, 80, 255, 120)),
        ]

        for idx, move in enumerate(self._moves[:5]):
            color = QColor(*color_defs[idx])
            self._paint_move_arrow(
                painter,
                color,
                move.from_square,
                move.to_square,
                flipped,
                left,
                top,
                cw,
                ch,
                f"{move.san}\n{move.score_display}",
            )

        painter.end()

    def _paint_move_arrow(
        self,
        painter,
        color,
        frm,
        to,
        flipped,
        left,
        top,
        cw,
        ch,
        label,
        shaft_width=5,
        arrow_size=15,
        fill_alpha=45,
        dash_from=True,
    ):
        fc, fr = sq_screen(frm, flipped)
        tc, tr = sq_screen(to, flipped)
        fx = int(left + fc * cw)
        fy = int(top + fr * ch)
        tx = int(left + tc * cw)
        ty = int(top + tr * ch)
        fcx = fx + int(cw / 2)
        fcy = fy + int(ch / 2)
        tcx = tx + int(cw / 2)
        tcy = ty + int(ch / 2)
        self._draw_arrow(
            painter,
            color,
            fcx,
            fcy,
            tcx,
            tcy,
            cw,
            ch,
            fx,
            fy,
            tx,
            ty,
            label=label,
            shaft_width=shaft_width,
            arrow_size=arrow_size,
            fill_alpha=fill_alpha,
            dash_from=dash_from,
        )
