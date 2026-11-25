"""Floating panel: buddy header, search box and sessions grouped by project."""

import time
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices, QGuiApplication, QKeyEvent, QKeySequence, QPalette, QShortcut, QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QSizeGrip, QSizePolicy, QStackedWidget,
    QToolButton, QTreeView, QVBoxLayout, QWidget,
)

from ..chat import ChatEvent
from ..models import SessionInfo, group_by_project
from ..scanner import ScanResult
from ..transcript import Entry, Transcript
from .chat_box import ChatBox
from .elided_label import ElidedLabel
from .icons import make_icon
from .mascot import Mascot
from .session_list import (
    GROUP_KEY_ROLE, SESSION_ROLE, SessionDelegate, SessionFilter, SessionTree, build_model, origin_label,
)
from .transcript_view import TranscriptView

AVATAR = 48
DEFAULT_SIZE = QSize(440, 640)
_REOPEN_GUARD_S = 0.35     # a tray click that just hid the panel must not reopen it
_RECENT_ACTIVITY_S = 120   # session written this recently may be open in VS Code / a terminal


def _busy_elsewhere_warning(session: SessionInfo) -> str | None:
    try:
        age = time.time() - session.file.stat().st_mtime
    except OSError:
        return None
    if age > _RECENT_ACTIVITY_S:
        return None
    return ("⚠ Esta sesión ha tenido actividad hace menos de 2 minutos: puede estar abierta en "
            "VS Code o en una terminal. Si escribes aquí a la vez, las respuestas se pueden mezclar.")


class Panel(QWidget):
    history_requested = Signal(object)      # SessionInfo
    terminal_requested = Signal(object)     # SessionInfo
    chat_send = Signal(object, str, str)    # SessionInfo, text, permission mode
    chat_stop = Signal()
    permission_answered = Signal(str, bool)
    mode_changed = Signal(str)
    refresh_requested = Signal()
    shown = Signal()
    hidden = Signal()

    def __init__(self, mascot: Mascot, menu: QMenu, standalone: bool = False) -> None:
        flags = (Qt.WindowType.Window if standalone else
                 Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        super().__init__(None, flags)
        self.setWindowTitle("Claude Buddy")
        self._standalone = standalone
        self._mascot = mascot
        self._hidden_at = 0.0
        self._pinned = False
        self._drag_offset: QPoint | None = None
        self._collapsed: set[str] = set()
        self._syncing = False
        self._signature: tuple | None = None
        self._total = 0
        self._activity = ""
        self._current: SessionInfo | None = None
        self._chat_status = ""
        if not standalone:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._build_ui(menu)
        self.resize(QSettings().value("panel/size", DEFAULT_SIZE))

        mascot.changed.connect(self._update_avatar)
        self._clock = QTimer(self, interval=60_000, timeout=self._tree_viewport_update)
        self._clock.start()
        self._message_timer = QTimer(self, singleShot=True, timeout=self._update_footer)

    # --- construction ----------------------------------------------------
    def _build_ui(self, menu: QMenu) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(objectName="card")
        card.setStyleSheet(
            "#card { background: palette(window); border: 1px solid palette(mid); border-radius: 10px; }"
            "QToolButton { border: none; padding: 5px; border-radius: 6px; background: transparent; }"
            "QToolButton:hover { background: rgba(128,128,128,0.18); }"
            "QToolButton:pressed { background: rgba(128,128,128,0.30); }"
            "QToolButton:checked { background: rgba(217,119,87,0.22); }"
            "QToolButton::menu-indicator { image: none; width: 0; }"
            # selection/hover are painted by SessionDelegate; keep the style's own highlight out
            "QTreeView { background: transparent; }"
            "QTreeView::item:selected, QTreeView::item:hover,"
            " QTreeView::branch:selected, QTreeView::branch:hover { background: transparent; }"
        )
        self._icon_buttons: list[tuple[QToolButton, str, bool]] = []
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 6)
        lay.setSpacing(8)

        # Header (also the drag handle of the frameless window)
        self._header = QWidget()
        head = QHBoxLayout(self._header)
        head.setContentsMargins(0, 0, 0, 0)
        self._avatar = QLabel()
        self._avatar.setFixedSize(AVATAR, AVATAR)
        head.addWidget(self._avatar)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        name = QLabel("Claude Buddy")
        font = name.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.15 if font.pointSizeF() > 0 else 11)
        name.setFont(font)
        self._status = ElidedLabel("Cargando sesiones…")
        self._status.setStyleSheet("color: palette(placeholder-text);")
        titles.addWidget(name)
        titles.addWidget(self._status)
        head.addLayout(titles, 1)

        refresh = self._tool_button("refresh", "Actualizar (F5)")
        refresh.clicked.connect(self.refresh_requested)
        head.addWidget(refresh)
        if not self._standalone:
            pin = self._tool_button("pin", "Mantener abierto", checkable=True)
            pin.toggled.connect(self._set_pinned)
            head.addWidget(pin)
        more = self._tool_button("more", "Opciones")
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        head.addWidget(more)
        if not self._standalone:
            close = self._tool_button("close", "Ocultar (Esc)")
            close.clicked.connect(self.hide)
            head.addWidget(close)
        lay.addWidget(self._header)

        # Two pages: session list / history of one session
        self._stack = QStackedWidget()
        lay.addWidget(self._stack, 1)
        list_page = QWidget()
        lp = QVBoxLayout(list_page)
        lp.setContentsMargins(0, 0, 0, 0)
        lp.setSpacing(8)

        self._search = QLineEdit(placeholderText="Buscar por título, proyecto o ID…", clearButtonEnabled=True)
        self._search.textChanged.connect(self._on_search)
        lp.addWidget(self._search)

        self._model = QStandardItemModel(self)
        self._proxy = SessionFilter(self)
        self._proxy.setSourceModel(self._model)
        self._tree = SessionTree(headerHidden=True, uniformRowHeights=False, indentation=14)
        self._tree.setModel(self._proxy)
        self._tree.setItemDelegate(SessionDelegate(self._tree))
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._tree.setFrameShape(QFrame.Shape.NoFrame)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)   # highlight = current row
        self._tree.setMouseTracking(True)
        self._tree.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)    # hover highlight in the delegate
        pal = self._tree.palette()                     # the style must not paint its own selection marks
        for role in (QPalette.ColorRole.Highlight, QPalette.ColorRole.Accent):
            pal.setColor(role, Qt.GlobalColor.transparent)
        self._tree.setPalette(pal)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        self._tree.activated.connect(self._on_activated)
        self._tree.expanded.connect(lambda i: self._track_expansion(i, True))
        self._tree.collapsed.connect(lambda i: self._track_expansion(i, False))
        lp.addWidget(self._tree, 1)

        self._empty = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self._empty.setStyleSheet("color: palette(placeholder-text); padding: 24px;")
        self._empty.hide()
        lp.addWidget(self._empty, 1)
        self._stack.addWidget(list_page)
        self._stack.addWidget(self._build_history_page())

        foot = QHBoxLayout()
        self._footer = QLabel()
        self._footer.setStyleSheet("color: palette(placeholder-text);")
        foot.addWidget(self._footer, 1)
        if not self._standalone:
            foot.addWidget(QSizeGrip(card), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        lay.addLayout(foot)

        QShortcut(QKeySequence("F5"), self, activated=self.refresh_requested)
        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._focus_search)
        QShortcut(QKeySequence.StandardKey.Back, self, activated=self.back_to_list)
        self._warnings: list[str] = []
        # Installed last: eventFilter relies on the widgets above existing
        self._header.installEventFilter(self)
        self._search.installEventFilter(self)

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        nav = QHBoxLayout()
        back = self._tool_button("back", "Volver a la lista (Esc)")
        back.clicked.connect(self.back_to_list)
        nav.addWidget(back, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self._h_title = ElidedLabel()
        bold = self._h_title.font()
        bold.setBold(True)
        self._h_title.setFont(bold)
        self._h_meta = ElidedLabel()
        self._h_meta.setStyleSheet("color: palette(placeholder-text);")
        texts.addWidget(self._h_title)
        texts.addWidget(self._h_meta)
        nav.addLayout(texts, 1)
        terminal = self._tool_button("terminal", "Abrir en terminal  (claude --resume)")
        terminal.clicked.connect(lambda: self._current and self.terminal_requested.emit(self._current))
        nav.addWidget(terminal, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(nav)
        self._view = TranscriptView()
        v.addWidget(self._view, 1)
        self._chat = ChatBox()
        self._chat.send_requested.connect(self._on_send)
        self._chat.stop_requested.connect(self.chat_stop)
        self._chat.permission_answered.connect(self.permission_answered)
        self._chat.mode_changed.connect(self.mode_changed)
        v.addWidget(self._chat)
        return page

    def _tool_button(self, icon_name: str, tip: str, checkable: bool = False) -> QToolButton:
        b = QToolButton(toolTip=tip, autoRaise=True, checkable=checkable)
        b.setIconSize(QSize(18, 18))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icon_buttons.append((b, icon_name, checkable))
        b.setIcon(make_icon(icon_name, self.palette().color(QPalette.ColorRole.WindowText), checkable))
        return b

    def _refresh_icons(self) -> None:
        color = self.palette().color(QPalette.ColorRole.WindowText)
        for button, name, checkable in self._icon_buttons:
            button.setIcon(make_icon(name, color, checkable))
        self._chat.refresh_icons()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "_chat"):
            self._refresh_icons()                      # light/dark theme switched

    # --- public API: history ------------------------------------------------
    @property
    def current_session(self) -> SessionInfo | None:
        return self._current

    def open_session(self, session: SessionInfo) -> None:
        self._current = session
        self._h_title.setText(session.title)
        self._h_title.setToolTip(f"{session.title}\nID: {session.session_id}")
        self._h_meta.setText(f"{session.project_name}  ·  {session.message_count} mensajes  ·  "
                             f"{origin_label(session.entrypoint)}")
        self._h_meta.setToolTip(session.cwd or "")
        self._view.show_placeholder("Cargando historial…")
        self._chat.set_banner(_busy_elsewhere_warning(session))
        self._chat.set_status("")
        self._stack.setCurrentIndex(1)
        self._chat.focus_input()
        self._update_footer()
        self.history_requested.emit(session)

    def update_current_session(self, session: SessionInfo) -> None:
        """The CLI moved the conversation to a new session id (fork)."""
        if self._current is not None:
            self._current = session
            self._h_title.setToolTip(f"{session.title}\nID: {session.session_id}")

    def on_chat_event(self, ev: ChatEvent) -> None:
        """Render live chat events; events for a session that is not open only update busy state."""
        if ev.kind == "busy":
            busy = ev.data["busy"]
            self._chat.set_busy(busy)
            self._chat.set_status("Claude está trabajando…  (■ para detener)" if busy else self._chat_status)
            if busy:
                self._chat_status = ""
            return
        if self._current is None or ev.session_id != self._current.session_id:
            return
        if ev.kind == "text_delta":
            self._view.stream_text(ev.text)
        elif ev.kind == "text":
            self._view.finish_text(ev.text)
        elif ev.kind == "tool":
            self._view.append_entry(Entry("tool", ev.text))
        elif ev.kind in ("tool_error", "error"):
            self._view.append_entry(Entry("error", ev.text))
            if ev.kind == "error":
                self._chat_status = "Error"
        elif ev.kind == "permission":
            self._chat.show_permission(ev.data["id"], ev.text)
        elif ev.kind == "result":
            if ev.data.get("is_error"):
                self._view.append_entry(Entry("error", ev.text or f"La respuesta terminó con error ({ev.data.get('subtype')})"))
                self._chat_status = "Terminó con error"
            else:
                cost = ev.data.get("cost")
                self._chat_status = "Listo" + (f"  ·  coste estimado {cost:.2f} US$" if cost else "")

    def _on_send(self, text: str, mode: str) -> None:
        if self._current is None:
            return
        self._view.append_entry(Entry("user", text, datetime.now(UTC)))
        self._chat.set_banner(None)            # user chose to go ahead; later activity is ours
        self.chat_send.emit(self._current, text, mode)

    def set_transcript(self, session: SessionInfo, transcript: Transcript, refresh: bool = False) -> None:
        if self._current is None or session.session_id != self._current.session_id:
            return                                      # user already moved on
        self._view.set_entries(transcript.entries, keep_scroll=refresh)
        if transcript.warnings:
            self.show_message("⚠ " + transcript.warnings[0], 8000)

    def back_to_list(self) -> None:
        if self._current is None:
            return
        self._current = None
        self._stack.setCurrentIndex(0)
        self._view.clear()                              # release the (possibly large) document
        self._update_footer()
        self._tree.setFocus()

    # --- public API: list ---------------------------------------------------
    def set_result(self, result: ScanResult) -> None:
        sessions = [s for s in result.sessions if s.message_count]   # empty sessions can't be resumed
        self._total = len(sessions)
        self._warnings = result.warnings
        signature = tuple((s.session_id, s.last_activity, s.message_count, s.title) for s in sessions)
        if signature != self._signature:
            self._signature = signature
            selected = self._selected_session_id()
            scroll = self._tree.verticalScrollBar().value()
            build_model(self._model, group_by_project(sessions))
            self._apply_expansion()
            self._select_session(selected)
            self._tree.verticalScrollBar().setValue(scroll)
        self._update_status()
        self._update_footer()

    def set_activity(self, text: str) -> None:
        self._activity = text
        self._update_status()

    def show_message(self, text: str, ms: int = 4000) -> None:
        self._footer.setText(text)
        self._footer.setToolTip("")
        self._message_timer.start(ms)

    def toggle(self, anchor: QRect | None = None) -> None:
        if self.isVisible():
            self.hide()
        elif time.monotonic() - self._hidden_at > _REOPEN_GUARD_S:
            self.show_near(anchor)

    def show_near(self, anchor: QRect | None = None) -> None:
        """Show next to `anchor` (tray icon or desktop pet), or bottom-right if unknown."""
        valid = anchor is not None and anchor.isValid() and not anchor.isEmpty()
        screen = (QGuiApplication.screenAt(anchor.center()) if valid else None) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        w = min(self.width(), avail.width() - 16)
        h = min(self.height(), avail.height() - 16)
        self.resize(w, h)
        if self._standalone and self.isVisible():
            pass
        elif valid:
            self.move(self.place(anchor, QSize(w, h), avail))
        elif not self._standalone:
            self.move(self._clamp(avail.right() - w - 12, avail.bottom() - h - 12, w, h, avail))
        self.show()
        self.raise_()
        self.activateWindow()
        self._focus_search()

    # --- events -----------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_avatar()
        self.shown.emit()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._hidden_at = time.monotonic()
        QSettings().setValue("panel/size", self.size())
        self.hidden.emit()

    def event(self, event: QEvent) -> bool:
        if (event.type() == QEvent.Type.WindowDeactivate and not self._standalone
                and not self._pinned and self.isVisible()):
            self.hide()
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._current is not None:
                self.back_to_list()
            elif self._search.text():
                self._search.clear()
            elif not self._standalone:
                self.hide()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._search and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Down:
            self._focus_first_session()
            return True
        if obj is self._header and not self._standalone:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
        return super().eventFilter(obj, event)

    # --- internals --------------------------------------------------------
    @classmethod
    def place(cls, anchor: QRect, size: QSize, avail: QRect, gap: int = 8) -> QPoint:
        """First side of `anchor` where the panel fits: above, below, left, right."""
        w, h = size.width(), size.height()
        cx, cy = anchor.center().x() - w // 2, anchor.center().y() - h // 2
        candidates = (
            (anchor.top() - gap - h >= avail.top(), cx, anchor.top() - gap - h),
            (anchor.bottom() + gap + h <= avail.bottom(), cx, anchor.bottom() + gap),
            (anchor.left() - gap - w >= avail.left(), anchor.left() - gap - w, cy),
            (anchor.right() + gap + w <= avail.right(), anchor.right() + gap, cy),
        )
        x, y = next(((x, y) for fits, x, y in candidates if fits), (cx, cy))
        return cls._clamp(x, y, w, h, avail)

    @staticmethod
    def _clamp(x: int, y: int, w: int, h: int, avail: QRect) -> QPoint:
        x = max(avail.left() + 8, min(x, avail.right() - w - 8))
        y = max(avail.top() + 8, min(y, avail.bottom() - h - 8))
        return QPoint(x, y)

    def _set_pinned(self, pinned: bool) -> None:
        self._pinned = pinned

    def _update_avatar(self) -> None:
        if self.isVisible():
            self._avatar.setPixmap(self._mascot.pixmap(AVATAR))

    def _tree_viewport_update(self) -> None:
        if self.isVisible():
            self._tree.viewport().update()      # refresh relative times

    def _focus_search(self) -> None:
        self.back_to_list()
        self._search.setFocus()
        self._search.selectAll()

    def _on_search(self, text: str) -> None:
        self._proxy.set_query(text)
        self._apply_expansion()
        self._update_status()

    def _visible_session_count(self) -> int:
        return sum(self._proxy.rowCount(self._proxy.index(r, 0)) for r in range(self._proxy.rowCount()))

    def _update_status(self) -> None:
        projects = self._model.rowCount()
        if self._proxy.query:
            text = f"{self._visible_session_count()} de {self._total} sesiones"
        else:
            text = f"{self._total} sesiones · {projects} proyectos"
        if self._activity:
            text += f" · {self._activity}"
        self._status.setText(text)

        if self._total == 0:
            self._show_empty("No hay sesiones de Claude Code todavía." if not self._warnings
                             else "No se encontraron sesiones.\n" + self._warnings[0])
        elif self._proxy.query and self._proxy.rowCount() == 0:
            self._show_empty(f"Sin resultados para «{self._proxy.query}».")
        else:
            self._show_empty(None)

    def _show_empty(self, text: str | None) -> None:
        self._empty.setText(text or "")
        self._empty.setVisible(text is not None)
        self._tree.setVisible(text is None)

    def _update_footer(self) -> None:
        if self._message_timer.isActive():
            return
        if self._current is not None:
            self._footer.setText("Esc o ← para volver a la lista")
            self._footer.setToolTip("")
        elif self._warnings:
            n = len(self._warnings)
            self._footer.setText(f"⚠ {n} aviso{'s' if n > 1 else ''}")
            self._footer.setToolTip("\n".join(self._warnings[:20]))
        else:
            self._footer.setText("Doble clic o Intro en una sesión para ver su historial")
            self._footer.setToolTip("")

    def _apply_expansion(self) -> None:
        self._syncing = True
        searching = bool(self._proxy.query)
        for r in range(self._proxy.rowCount()):
            idx = self._proxy.index(r, 0)
            self._tree.setExpanded(idx, searching or idx.data(GROUP_KEY_ROLE) not in self._collapsed)
        self._syncing = False

    def _track_expansion(self, index, expanded: bool) -> None:
        key = index.data(GROUP_KEY_ROLE)
        if self._syncing or self._proxy.query or key is None:
            return
        (self._collapsed.discard if expanded else self._collapsed.add)(key)

    def _session_at(self, index) -> SessionInfo | None:
        return index.data(SESSION_ROLE) if index.isValid() else None

    def _selected_session_id(self) -> str | None:
        s = self._session_at(self._tree.currentIndex())
        return s.session_id if s else None

    def _select_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        for r in range(self._proxy.rowCount()):
            group = self._proxy.index(r, 0)
            for c in range(self._proxy.rowCount(group)):
                idx = self._proxy.index(c, 0, group)
                s = self._session_at(idx)
                if s and s.session_id == session_id:
                    self._tree.setCurrentIndex(idx)
                    return

    def _focus_first_session(self) -> None:
        if self._proxy.rowCount():
            first = self._proxy.index(0, 0, self._proxy.index(0, 0))
            if first.isValid():
                self._tree.setFocus()
                self._tree.setCurrentIndex(first)

    def _on_activated(self, index) -> None:
        if s := self._session_at(index):
            self.open_session(s)

    def _context_menu(self, pos: QPoint) -> None:
        index = self._tree.indexAt(pos)
        if not index.isValid():
            return
        session = self._session_at(index)
        cwd = session.cwd if session else index.data(Qt.ItemDataRole.ToolTipRole)
        menu = QMenu(self)
        if session:
            menu.addAction("Abrir en terminal", lambda: self.terminal_requested.emit(session))
            menu.addAction("Copiar ID de sesión",
                           lambda: QGuiApplication.clipboard().setText(session.session_id))
        if cwd and Path(cwd).is_dir():
            menu.addAction("Abrir carpeta del proyecto",
                           lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(cwd)))
        if not menu.isEmpty():
            menu.exec(self._tree.viewport().mapToGlobal(pos))
