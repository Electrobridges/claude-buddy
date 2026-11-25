"""Qt renderer and animator for the pixel buddy."""

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from . import sprites

ICON_SIZES = (16, 32, 48, 64)


def render(grid: tuple[str, ...], skin: str, size: int) -> QPixmap:
    """Render a frame with crisp pixels; size is rounded down to a multiple of 16 when possible."""
    pal = {k: QColor(v) for k, v in sprites.palette(skin).items()}
    scale = max(1, size // sprites.SIZE)
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    offset = (size - scale * sprites.SIZE) // 2
    painter = QPainter(image)
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch != "." and ch in pal:
                painter.fillRect(offset + x * scale, offset + y * scale, scale, scale, pal[ch])
    painter.end()
    return QPixmap.fromImage(image)


class Mascot(QObject):
    """Holds state + skin, ticks the animation and emits `changed` only when the image changes.

    Shown state = override (drag/hover) > flash (short reactions) > base (what Claude is doing).
    """

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = "idle"
        self._base = "idle"
        self._override: str | None = None
        self._flash: str | None = None
        self._flash_timer = QTimer(self, singleShot=True, timeout=self._end_flash)
        self._skin = "terracotta"
        self._accessory = "none"
        self._index = 0
        self._animate = True
        self._grid = sprites.frame("idle", 0)
        self._cache: dict[tuple, QPixmap] = {}
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._restart()

    # --- properties -------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def skin(self) -> str:
        return self._skin

    @property
    def accessory(self) -> str:
        return self._accessory

    @property
    def base_state(self) -> str:
        return self._base

    def set_state(self, state: str) -> None:
        """Base state, driven by what Claude is doing."""
        if state in sprites.STATES:
            self._base = state
            self._apply()

    def set_override(self, state: str | None) -> None:
        """Interaction state (drag, hover) that wins over everything while set."""
        if state is None or state in sprites.STATES:
            self._override = state
            self._apply()

    def flash(self, state: str, ms: int) -> None:
        """Short reaction (done, error, greeting) shown for `ms`, then back to the base state."""
        if state in sprites.STATES:
            self._flash = state
            self._flash_timer.start(ms)
            self._apply()

    def _end_flash(self) -> None:
        self._flash = None
        self._apply()

    def _apply(self) -> None:
        state = self._override or self._flash or self._base
        if state != self._state:
            self._state, self._index = state, 0
            self._restart()

    def set_skin(self, skin: str | None = None, accessory: str | None = None) -> None:
        if skin in sprites.SKINS:
            self._skin = skin
        if accessory in sprites.ACCESSORIES:
            self._accessory = accessory
        self._update(force=True)

    def set_animated(self, on: bool) -> None:
        self._animate = on
        self._index = 0
        self._restart()

    # --- rendering --------------------------------------------------------
    def pixmap(self, size: int) -> QPixmap:
        key = (self._grid, self._skin, size)
        if key not in self._cache:
            if len(self._cache) > 400:
                self._cache.clear()
            self._cache[key] = render(self._grid, self._skin, size)
        return self._cache[key]

    def icon(self) -> QIcon:
        icon = QIcon()
        for size in ICON_SIZES:
            icon.addPixmap(self.pixmap(size))
        return icon

    # --- animation --------------------------------------------------------
    def _restart(self) -> None:
        self._timer.stop()
        if self._animate:
            self._timer.start(sprites.STATES[self._state].interval_ms)
        self._update(force=True)

    def _tick(self) -> None:
        self._index += 1
        self._update()

    def _update(self, force: bool = False) -> None:
        grid = sprites.frame(self._state, self._index, self._accessory)
        if force or grid != self._grid:
            self._grid = grid
            self.changed.emit()
