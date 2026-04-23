"""
board_selector.py
Tries to auto-detect the board position from the page.
Falls back to click-drag if auto-detect fails.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRect, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import QWidget, QApplication

from config import Config


class BoardSelectorWindow(QWidget):
    board_selected = pyqtSignal(tuple)

    def __init__(self, config: Config, vision=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.vision = vision
        self._origin = None
        self._current = None
        self._drag_mode = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(QApplication.primaryScreen().geometry())

    def show(self):
        super().show()
        # Try auto-detect first after short delay
        QTimer.singleShot(400, self._try_auto)

    def _try_auto(self):
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
                print(f"[Selector] Auto-detect failed: {e}")

        print("[Selector] Could not auto-detect — please drag over the board.")
        self._drag_mode = True
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._origin:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._origin:
            rect = QRect(self._origin, event.pos()).normalized()
            if rect.width() > 30 and rect.height() > 30:
                tl = self.mapToGlobal(rect.topLeft())
                br = self.mapToGlobal(rect.bottomRight())
                result = (tl.x(), tl.y(), br.x(), br.y())
                self.config.board_rect = result
                self.hide()
                self.board_selected.emit(result)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        if self._origin and self._current:
            rect = QRect(self._origin, self._current).normalized()
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, QColor(0, 0, 0, 0))
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(0, 255, 100), 3))
            painter.drawRect(rect)
        else:
            msg = ("Drag a box around the chess board\nthen release"
                   if self._drag_mode else
                   "Detecting board position automatically...")
            painter.setFont(QFont("Arial", 20, QFont.Weight.Bold))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, msg)

        painter.end()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()