"""Pet mode: drives the desktop buddy with PetBrain (walking, falling, poops, petting, moods)."""

import time

from PySide6.QtCore import QElapsedTimer, QObject, QPoint, QRect, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QToolTip, QWidget

from ..pet import Needs, PetBrain, ReversalDetector, World
from . import sprites
from .desktop_buddy import DesktopBuddy
from .mascot import Mascot, render

TICK_MS = 40
MAX_POOPS = 8


class PoopWindow(QWidget):
    """A poop left on the desktop. Click to clean it."""

    cleaned = Signal(object)

    def __init__(self, size: int, skin: str) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clic para limpiar")
        self._frames = [render(sprites.poop_frame(i), skin, size) for i in range(2)]
        self._index = 0
        self._timer = QTimer(self, interval=600, timeout=self._animate)
        self._timer.start()

    def _animate(self) -> None:
        self._index = 1 - self._index
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        QPainter(self).drawPixmap(0, 0, self._frames[self._index])

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.cleaned.emit(self)


class PetController(QObject):
    state_changed = Signal()

    def __init__(self, desktop: DesktopBuddy, mascot: Mascot, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._desktop = desktop
        self._mascot = mascot
        self._brain: PetBrain | None = None
        self._paused = False
        self._sprite: str | None = None
        self._poops: list[PoopWindow] = []
        self._stroke = ReversalDetector(min_travel=6, reversals=3, window=1.6)
        self._shake = ReversalDetector(min_travel=30, reversals=4, window=1.0)
        self._clock = QElapsedTimer()
        self._saved_at = 0.0
        self._timer = QTimer(self, interval=TICK_MS, timeout=self._tick)
        desktop.drag_started.connect(self._on_drag_started)
        desktop.drag_moved.connect(self._on_drag_moved)
        desktop.drag_released.connect(self._on_drag_released)
        desktop.hover_moved.connect(self._on_hover)

    # --- public -------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._brain is not None

    @property
    def sprite_state(self) -> str | None:
        return self._brain.sprite_state if self._brain else None

    @property
    def needs(self) -> Needs | None:
        return self._brain.needs if self._brain else None

    @property
    def poop_count(self) -> int:
        return len(self._poops)

    def set_enabled(self, on: bool) -> None:
        if on == self.enabled:
            return
        if on:
            pos = self._desktop.pos()
            self._brain = PetBrain(float(pos.x()), float(pos.y()), needs=self._load_needs())
            self._desktop.pet_mode = True
            self._mascot.set_override(None)
            self._clock.start()
            self._timer.start()
        else:
            self._save_needs()
            self._timer.stop()
            self._brain = None
            self._desktop.pet_mode = False
            self._desktop.set_facing(1)
            self._desktop.save_position()
        self._emit_if_changed(force=True)

    def set_paused(self, paused: bool) -> None:
        """Panel open or Claude working: the pet stays where it is."""
        self._paused = paused

    def feed(self) -> None:
        if self._brain and self._brain.feed():
            self._emit_if_changed()
        self._flush_events()

    def chase(self) -> None:
        if self._brain:
            self._brain.chase()
            self._emit_if_changed()

    def clean_all(self) -> None:
        for poop in list(self._poops):
            self._clean(poop)

    def shutdown(self) -> None:
        self._save_needs()
        for poop in self._poops:
            poop.close()
        self._poops.clear()

    # --- simulation ---------------------------------------------------------
    def _world(self) -> World:
        d = self._desktop
        screen = QGuiApplication.screenAt(d.geometry().center()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        scale = d.width() / sprites.SIZE
        floor = avail.bottom() + 1 - 15 * scale                   # feet (row 14) on the taskbar
        cursor = QCursor.pos()
        cursor_x = cursor.x() - d.width() / 2 if avail.contains(cursor) else None
        return World(floor_y=floor, min_x=avail.left(), max_x=avail.right() + 1 - d.width(),
                     cursor_x=cursor_x, paused=self._paused)

    def _tick(self) -> None:
        brain = self._brain
        if brain is None or not self._desktop.isVisible():
            return
        dt = self._clock.restart() / 1000.0
        if not self._desktop.dragging:
            brain.tick(dt, self._world())
            target = QPoint(round(brain.x), round(brain.y))
            if target != self._desktop.pos():
                self._desktop.move(target)
            self._desktop.set_facing(brain.facing)
        self._flush_events()
        self._emit_if_changed()
        if time.monotonic() - self._saved_at > 30:
            self._save_needs()

    def _flush_events(self) -> None:
        if not self._brain:
            return
        events, self._brain.events = self._brain.events, []
        for event in events:
            if event[0] == "poop":
                self._spawn_poop(event[1], event[2])
            elif event[0] == "say":
                self._say(event[1])

    def _emit_if_changed(self, force: bool = False) -> None:
        sprite = self.sprite_state
        if force or sprite != self._sprite:
            self._sprite = sprite
            self.state_changed.emit()
        if self._brain:
            self._desktop.setToolTip(f"Claude Buddy · {self._brain.needs.summary()}\n"
                                     "Acaríciame moviendo el ratón encima · Clic: sesiones")

    def _say(self, text: str) -> None:
        d = self._desktop
        QToolTip.showText(d.mapToGlobal(QPoint(d.width() // 2, 0)), text, d, QRect(), 1800)

    # --- poops --------------------------------------------------------------
    def _spawn_poop(self, x: float, pet_y: float) -> None:
        size = self._desktop.width() // 2
        poop = PoopWindow(size, self._mascot.skin)
        scale = size / sprites.SIZE
        poop.move(round(x + self._desktop.width() / 2 - size / 2),
                  round(pet_y + 15 * scale * 2 - 15 * scale))            # same floor as the pet
        poop.cleaned.connect(self._clean)
        poop.show()
        self._desktop.raise_()
        self._poops.append(poop)
        if len(self._poops) > MAX_POOPS:
            self._poops.pop(0).close()

    def _clean(self, poop: PoopWindow) -> None:
        if poop in self._poops:
            self._poops.remove(poop)
            poop.close()
            if self._brain:
                self._brain.poop_cleaned()

    # --- gestures -----------------------------------------------------------
    def _on_hover(self, pos: QPoint) -> None:
        if self._brain and self._stroke.feed(pos.x(), time.monotonic()):
            self._brain.petted()
            self._flush_events()
            self._emit_if_changed()

    def _on_drag_started(self) -> None:
        if self._brain:
            self._shake.reset()
            self._brain.grab()
            self._emit_if_changed()

    def _on_drag_moved(self, pos: QPoint) -> None:
        if self._brain:
            self._brain.drag_to(float(pos.x()), float(pos.y()))
            if self._shake.feed(pos.x(), time.monotonic()):
                self._brain.shaken()
                self._mascot.set_override("dizzy")
                self._flush_events()

    def _on_drag_released(self, pos: QPoint) -> None:
        if self._brain:
            self._brain.release(float(pos.x()), float(pos.y()), self._world())
            self._clock.restart()
            self._emit_if_changed()

    # --- persistence --------------------------------------------------------
    def _load_needs(self) -> Needs:
        s = QSettings()
        needs = Needs(float(s.value("pet/hunger", 20)), float(s.value("pet/happiness", 70)),
                      float(s.value("pet/energy", 80)))
        saved_at = float(s.value("pet/saved_at", 0) or 0)
        if saved_at:
            needs.advance_offline(time.time() - saved_at)
        return needs

    def _save_needs(self) -> None:
        if not self._brain:
            return
        n, s = self._brain.needs, QSettings()
        s.setValue("pet/hunger", n.hunger)
        s.setValue("pet/happiness", n.happiness)
        s.setValue("pet/energy", n.energy)
        s.setValue("pet/saved_at", time.time())
        self._saved_at = time.monotonic()
