"""
board_selector.py
Auto-detects the board from the page DOM.
Falls back to a clean click-drag UI with square-lock snapping.
"""
from __future__ import annotations
import math
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import pyqtSignal

from config import Config


class BoardSelectorWindow(QWidget):
    board_selected = pyqtSignal(tuple)

    def __init__(self, config: Config, vision=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.vision = vision
        self._origin  = None
        self._current = None
        self._drag_mode = False
        self._status_msg = "Detecting board position automatically..."
        self._auto_attempts = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(QApplication.primaryScreen().geometry())

    # ── Show / Auto-detect ────────────────────────────────────────────────

    def show(self):
        super().show()
        QTimer.singleShot(500, self._try_auto)

    def _try_auto(self):
        self._auto_attempts += 1
        if self.vision:
            try:
                rect = self.vision.get_board_rect_from_page()
                if rect and (rect[2] - rect[0]) > 100:
                    print(f"[Selector] Board auto-detected at {rect}")
                    self.config.board_rect = rect
                    self.hide()
                    self.board_selected.emit(rect)
                    return
            except Exception as e:
                print(f"[Selector] Auto-detect error: {e}")

        # Retry once more after 800ms before giving up
        if self._auto_attempts < 3:
            self._status_msg = (
                f"Auto-detecting... (attempt {self._auto_attempts}/3)"
            )
            self.update()
            QTimer.singleShot(800, self._try_auto)
        else:
            print("[Selector] Auto-detect failed — switching to drag mode.")
            self._status_msg = ""
            self._drag_mode = True
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()

    # ── Mouse events ──────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if not self._drag_mode:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin  = event.pos()
            self._current = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._origin:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._origin:
            raw = QRect(self._origin, event.pos()).normalized()

            # Square-lock: force the selection to be square
            side = max(raw.width(), raw.height())
            locked = QRect(raw.topLeft(), raw.topLeft())
            locked.setWidth(side)
            locked.setHeight(side)

            if locked.width() > 30:
                tl = self.mapToGlobal(locked.topLeft())
                br = self.mapToGlobal(locked.bottomRight())
                result = (tl.x(), tl.y(), br.x(), br.y())
                self.config.board_rect = result
                self.hide()
                self.board_selected.emit(result)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
        # Press R to retry auto-detect at any time
        elif key == Qt.Key.Key_R:
            self._auto_attempts = 0
            self._drag_mode = False
            self._origin = None
            self._current = None
            self._status_msg = "Retrying auto-detect..."
            self.update()
            QTimer.singleShot(300, self._try_auto)

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        screen = self.rect()

        if self._origin and self._current:
            # ── Active drag ───────────────────────────────────────────────
            raw  = QRect(self._origin, self._current).normalized()
            side = max(raw.width(), raw.height())
            sel  = QRect(raw.topLeft(), raw.topLeft())
            sel.setWidth(side)
            sel.setHeight(side)

            # Dim everything outside selection
            painter.fillRect(screen, QColor(0, 0, 0, 150))

            # Clear selection area
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(sel, QColor(0, 0, 0, 0))
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)

            # 8×8 grid preview inside selection
            cw = sel.width()  / 8
            ch = sel.height() / 8
            painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
            for i in range(1, 8):
                x = int(sel.left() + i * cw)
                y = int(sel.top()  + i * ch)
                painter.drawLine(x, sel.top(),  x, sel.bottom())
                painter.drawLine(sel.left(), y, sel.right(), y)

            # Outer border
            painter.setPen(QPen(QColor(0, 255, 100), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel)

            # Corner handles
            handle_size = 8
            painter.setBrush(QBrush(QColor(0, 255, 100)))
            painter.setPen(Qt.PenStyle.NoPen)
            for cx, cy in [
                (sel.left(),  sel.top()),
                (sel.right(), sel.top()),
                (sel.left(),  sel.bottom()),
                (sel.right(), sel.bottom()),
            ]:
                painter.drawEllipse(
                    cx - handle_size // 2, cy - handle_size // 2,
                    handle_size, handle_size)

            # Size label
            painter.setFont(QFont("Arial", 11))
            painter.setPen(QColor(200, 255, 200))
            painter.drawText(
                sel.left() + 4, sel.top() - 6,
                f"{side} × {side}px"
            )

        elif self._drag_mode:
            # ── Drag instructions ─────────────────────────────────────────
            painter.fillRect(screen, QColor(0, 0, 0, 140))

            # Crosshair guides following... actually static centre hint
            cx, cy = screen.width() // 2, screen.height() // 2
            painter.setPen(QPen(QColor(255, 255, 255, 30), 1,
                                Qt.PenStyle.DashLine))
            painter.drawLine(0, cy, screen.width(), cy)
            painter.drawLine(cx, 0, cx, screen.height())

            # Main instruction box
            box_w, box_h = 480, 140
            box = QRect(cx - box_w // 2, cy - box_h // 2, box_w, box_h)
            painter.setBrush(QBrush(QColor(20, 20, 20, 200)))
            painter.setPen(QPen(QColor(0, 200, 80), 2))
            painter.drawRoundedRect(box, 12, 12)

            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 18, QFont.Weight.Bold))
            painter.drawText(box.adjusted(0, 10, 0, 0),
                             Qt.AlignmentFlag.AlignHCenter |
                             Qt.AlignmentFlag.AlignTop,
                             "Click and drag over the chess board")

            painter.setFont(QFont("Arial", 12))
            painter.setPen(QColor(160, 220, 160))
            painter.drawText(box.adjusted(0, 55, 0, 0),
                             Qt.AlignmentFlag.AlignHCenter |
                             Qt.AlignmentFlag.AlignTop,
                             "Selection is locked to a square automatically")

            painter.setFont(QFont("Arial", 11))
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(box.adjusted(0, 85, 0, 0),
                             Qt.AlignmentFlag.AlignHCenter |
                             Qt.AlignmentFlag.AlignTop,
                             "Press R to retry auto-detect   •   Esc to cancel")

        else:
            # ── Auto-detecting spinner ────────────────────────────────────
            painter.fillRect(screen, QColor(0, 0, 0, 140))
            cx, cy = screen.width() // 2, screen.height() // 2

            box_w, box_h = 400, 90
            box = QRect(cx - box_w // 2, cy - box_h // 2, box_w, box_h)
            painter.setBrush(QBrush(QColor(20, 20, 20, 210)))
            painter.setPen(QPen(QColor(70, 130, 255), 2))
            painter.drawRoundedRect(box, 12, 12)

            painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(box.adjusted(0, 8, 0, 0),
                             Qt.AlignmentFlag.AlignHCenter |
                             Qt.AlignmentFlag.AlignTop,
                             self._status_msg or "Detecting board...")

            painter.setFont(QFont("Arial", 11))
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(box.adjusted(0, 50, 0, 0),
                             Qt.AlignmentFlag.AlignHCenter |
                             Qt.AlignmentFlag.AlignTop,
                             "Press R to retry   •   Esc to cancel")

        painter.end()