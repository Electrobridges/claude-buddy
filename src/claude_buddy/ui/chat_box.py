"""Message box under the history: input, send/stop, permission prompts, permission mode."""

from html import escape

from PySide6.QtCore import QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from ..chat import PERMISSION_MODES
from .elided_label import ElidedLabel
from .icons import ACCENT, make_icon


class _Input(QPlainTextEdit):
    submit = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if enter and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submit.emit()
            return
        super().keyPressEvent(event)


class ChatBox(QWidget):
    send_requested = Signal(str, str)        # text, permission mode
    stop_requested = Signal()
    permission_answered = Signal(str, bool)  # request id, allowed
    mode_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._perm_id: str | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._banner = QLabel(wordWrap=True)
        self._banner.setStyleSheet("background: rgba(242,193,78,0.22); border-radius: 6px; padding: 6px;")
        self._banner.hide()
        lay.addWidget(self._banner)

        # Permission request (replaces Claude Code's interactive prompt)
        self._perm = QFrame()
        self._perm.setStyleSheet("QFrame { background: rgba(217,119,87,0.16); border-radius: 6px; }")
        perm = QVBoxLayout(self._perm)
        perm.setContentsMargins(8, 6, 8, 6)
        self._perm_text = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText)
        self._perm_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        perm.addWidget(self._perm_text)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        deny = QPushButton("Denegar")
        deny.clicked.connect(lambda: self._answer(False))
        self._allow = QPushButton("Permitir")
        self._allow.setDefault(True)
        self._allow.clicked.connect(lambda: self._answer(True))
        buttons.addWidget(deny)
        buttons.addWidget(self._allow)
        perm.addLayout(buttons)
        self._perm.hide()
        lay.addWidget(self._perm)

        row = QHBoxLayout()
        self._input = _Input(placeholderText="Escribe para continuar la sesión…  (Intro envía · Mayús+Intro, nueva línea)")
        self._input.setFixedHeight(64)
        self._input.submit.connect(self._submit)
        row.addWidget(self._input, 1)
        side = QVBoxLayout()
        self._send = QToolButton(toolTip="Enviar (Intro)", autoRaise=True)
        self._send.clicked.connect(self._submit)
        self._stop = QToolButton(toolTip="Detener la respuesta", autoRaise=True)
        self._stop.clicked.connect(self.stop_requested)
        for button in (self._send, self._stop):
            button.setIconSize(QSize(22, 22))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_icons()
        self._stop.hide()
        side.addWidget(self._send)
        side.addWidget(self._stop)
        side.addStretch(1)
        row.addLayout(side)
        lay.addLayout(row)

        bottom = QHBoxLayout()
        self._mode = QComboBox(toolTip="Qué puede hacer Claude sin preguntarte")
        for key, label in PERMISSION_MODES.items():
            self._mode.addItem(f"Permisos: {label}", key)
        saved = QSettings().value("chat/mode", "default")
        self._mode.setCurrentIndex(max(0, self._mode.findData(saved)))
        self._mode.currentIndexChanged.connect(self._on_mode)
        bottom.addWidget(self._mode)
        self._status = ElidedLabel()
        self._status.setStyleSheet("color: palette(placeholder-text);")
        bottom.addWidget(self._status, 1)
        lay.addLayout(bottom)

    # --- public -------------------------------------------------------------
    def refresh_icons(self) -> None:
        self._send.setIcon(make_icon("send", ACCENT))
        self._stop.setIcon(make_icon("stop", QColor("#D64545")))

    @property
    def mode(self) -> str:
        return self._mode.currentData()

    def focus_input(self) -> None:
        self._input.setFocus()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._send.setEnabled(not busy)
        self._stop.setVisible(busy)
        self._mode.setEnabled(not busy)
        if not busy:
            self.clear_permission()

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def set_banner(self, text: str | None) -> None:
        self._banner.setText(text or "")
        self._banner.setVisible(bool(text))

    def show_permission(self, request_id: str, summary: str) -> None:
        self._perm_id = request_id
        self._perm_text.setText(f"Claude quiere usar:<br><b>{escape(summary)}</b>")
        self._perm.show()
        self._allow.setFocus()

    def clear_permission(self) -> None:
        self._perm_id = None
        self._perm.hide()

    # --- internals ----------------------------------------------------------
    def _submit(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or self._busy:
            return
        self._input.clear()
        self.send_requested.emit(text, self.mode)

    def _answer(self, allowed: bool) -> None:
        if self._perm_id:
            self.permission_answered.emit(self._perm_id, allowed)
        self.clear_permission()
        self._input.setFocus()

    def _on_mode(self) -> None:
        QSettings().setValue("chat/mode", self.mode)
        self.mode_changed.emit(self.mode)
