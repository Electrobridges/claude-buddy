"""Always-on-top desktop pet: transparent, draggable anywhere, click opens the panel."""

from PySide6.QtCore import QPoint, QSettings, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QGuiApplication, QMouseEvent, QPainter, QPaintEvent, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from .mascot import Mascot

SIZES = {64: "Pequeño", 96: "Mediano", 128: "Grande"}     # multiples of 16 keep pixels crisp
DEFAULT_SIZE = 96
_MARGIN = 24


class DesktopBuddy(QWidget):
    clicked = Signal()
    drag_started = Signal()
    drag_moved = Signal(QPoint)          # new window position
    drag_released = Signal(QPoint)       # final window position
    hover_moved = Signal(QPoint)         # cursor position while over the pet (no button pressed)

    def __init__(self, mascot: Mascot, menu: QMenu, size: int = DEFAULT_SIZE) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setWindowTitle("Claude Buddy")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)                       # petting = rubbing the cursor over it
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Claude Buddy\nClic: ver sesiones · Arrastrar: mover · Clic derecho: menú")
        self._mascot = mascot
        self._menu = menu
        self._press: QPoint | None = None
        self._offset = QPoint()
        self._dragging = False
        self._facing = 1
        self._mirrored: tuple[int, QPixmap] | None = None
        self.pet_mode = False                             # set by PetController
        mascot.changed.connect(self.update)
        self.setFixedSize(size if size in SIZES else DEFAULT_SIZE, size if size in SIZES else DEFAULT_SIZE)
        self._restore_position()

    # --- public -------------------------------------------------------------
    @property
    def dragging(self) -> bool:
        return self._dragging

    def set_facing(self, facing: int) -> None:
        if facing != self._facing:
            self._facing = facing
            self.update()

    def set_size(self, size: int) -> None:
        if size not in SIZES or size == self.width():
            return
        bottom_center = self.geometry().center().x(), self.geometry().bottom()
        self.setFixedSize(size, size)
        self.move(bottom_center[0] - size // 2, bottom_center[1] - size + 1)   # grow upwards
        self.ensure_visible()
        self.save_position()

    def ensure_visible(self) -> None:
        """Bring the pet back if its screen disappeared (monitor unplugged, resolution change)."""
        if QGuiApplication.screenAt(self.geometry().center()) is None:
            self.move(self._default_position())
            self.save_position()

    def save_position(self) -> None:
        QSettings().setValue("mascot/pos", self.pos())

    # --- painting & mouse ---------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:
        pixmap = self._mascot.pixmap(self.width())
        if self._facing < 0:                              # walking left: mirror the sprite
            key = pixmap.cacheKey()
            if self._mirrored is None or self._mirrored[0] != key:
                self._mirrored = (key, pixmap.transformed(QTransform().scale(-1, 1)))
            pixmap = self._mirrored[1]
        QPainter(self).drawPixmap(0, 0, pixmap)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._offset = self._press - self.pos()
            self._dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.globalPosition().toPoint()
        if self._press is None:
            if not event.buttons():
                self.hover_moved.emit(pos)
            return
        if not self._dragging and (pos - self._press).manhattanLength() >= QApplication.startDragDistance():
            self._dragging = True
            self._mascot.set_override("dragged")
            self.drag_started.emit()
        if self._dragging:
            self.move(pos - self._offset)
            self.drag_moved.emit(self.pos())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self._dragging:
            self.ensure_visible()
            self.save_position()
            self._mascot.set_override("hover" if self.underMouse() and not self.pet_mode else None)
            self._press, self._dragging = None, False
            self.drag_released.emit(self.pos())
        else:
            self._press = None
            self.clicked.emit()

    def enterEvent(self, event) -> None:
        if not self._dragging and not self.pet_mode:     # in pet mode, rubbing = petting instead
            self._mascot.set_override("hover")

    def leaveEvent(self, event) -> None:
        if not self._dragging and not self.pet_mode:
            self._mascot.set_override(None)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._menu.exec(event.globalPos())

    # --- position persistence ----------------------------------------------
    def _default_position(self) -> QPoint:
        avail = QGuiApplication.primaryScreen().availableGeometry()
        return QPoint(avail.right() - self.width() - _MARGIN, avail.bottom() - self.height() - _MARGIN)

    def _restore_position(self) -> None:
        saved = QSettings().value("mascot/pos")
        self.move(saved if isinstance(saved, QPoint) else self._default_position())
        self.ensure_visible()
