"""Claude Buddy desktop app: tray icon + floating sessions panel."""

import getpass
import logging
import re
import sys
import time
from functools import partial
from pathlib import Path

from dataclasses import replace

from PySide6.QtCore import QObject, QRect, QSettings, QStandardPaths, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__
from .chat import ChatEngine, ChatEvent
from .models import SessionInfo
from .platform_setup import hide_child_consoles, setup_logging
from .terminal import TerminalError, open_in_terminal
from .scanner import ScanResult, newest_mtime
from .ui import sprites
from .ui.desktop_buddy import DEFAULT_SIZE, SIZES, DesktopBuddy
from .ui.loader import IndexLoader, TranscriptLoader
from .ui.mascot import Mascot, render
from .ui.panel import Panel
from .ui.pet_controller import PetController

APP_ID = "ClaudeBuddy"
ACTIVITY_POLL_MS = 3000
WORKING_SECS = 15          # a session file written this recently = Claude is working
DONE_SECS = 6              # celebrate briefly when work stops
SLEEP_SECS = 30 * 60       # no activity for this long = buddy falls asleep
HISTORY_REFRESH_SECS = 5   # minimum gap between live reloads of the open history


def _file_stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


class _ChatBridge(QObject):
    """Carries ChatEngine events from its asyncio thread to the GUI thread."""
    event = Signal(object)


class Buddy(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self._settings = QSettings()
        self._sessions = 0
        self._last_write: float | None = None
        self._was_working = False
        self._done_until = 0.0

        self.mascot = Mascot(self)
        self.mascot.set_skin(str(self._settings.value("mascot/skin", "terracotta")),
                             str(self._settings.value("mascot/accessory", "none")))
        self.mascot.set_animated(self._settings.value("mascot/animate", True, type=bool))

        self.loader = IndexLoader(parent=self)
        self.menu = self._build_menu()

        has_tray = QSystemTrayIcon.isSystemTrayAvailable()
        self.panel = Panel(self.mascot, self.menu, standalone=not has_tray)
        self.tray: QSystemTrayIcon | None = None
        if has_tray:
            self.tray = QSystemTrayIcon(self.mascot.icon(), self)
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()
        app.setWindowIcon(self.mascot.icon())

        self.desktop = DesktopBuddy(self.mascot, self.menu, self._settings.value("mascot/size", DEFAULT_SIZE, type=int))
        self.desktop.clicked.connect(lambda: self.panel.toggle(self.desktop.frameGeometry()))
        app.screenRemoved.connect(lambda _screen: self.desktop.ensure_visible())
        if self._desktop_enabled():
            self.desktop.show()

        # Pet mode: the desktop buddy walks, poops, wants food and cuddles
        self.pet = PetController(self.desktop, self.mascot, self)
        self.pet.state_changed.connect(self._update_state)
        self.panel.shown.connect(self._sync_pet_pause)
        self.panel.hidden.connect(self._sync_pet_pause)

        self.mascot.changed.connect(self._on_mascot_changed)
        self.loader.loaded.connect(self._on_loaded)
        self.loader.busy_changed.connect(lambda _: self._update_state())
        self.panel.refresh_requested.connect(self._refresh_all)
        self.panel.shown.connect(self.loader.request)

        self.history = TranscriptLoader(parent=self)
        self._history_stamp: tuple[int, int] | None = None
        self._history_checked = 0.0
        self.panel.history_requested.connect(self._load_history)
        self.history.loaded.connect(self.panel.set_transcript)
        self.history.busy_changed.connect(lambda _: self._update_state())

        # Live chat (claude-agent-sdk runs in its own thread; events come back queued)
        self._chat_bridge = _ChatBridge(self)
        self._chat_bridge.event.connect(self._on_chat_event, Qt.ConnectionType.QueuedConnection)
        self.chat = ChatEngine(self._chat_bridge.event.emit)
        self._chat_activity: str | None = None
        self._ignore_activity_until = 0.0
        self.panel.chat_send.connect(self._chat_send)
        self.panel.chat_stop.connect(self.chat.interrupt)
        self.panel.permission_answered.connect(self.chat.answer_permission)
        self.panel.mode_changed.connect(self.chat.set_mode)
        self.panel.terminal_requested.connect(self._open_terminal)

        self._activity_timer = QTimer(self, interval=ACTIVITY_POLL_MS, timeout=self._poll_activity)
        self._activity_timer.start()
        self.loader.request()
        if self._settings.value("mascot/petmode", False, type=bool) and self._desktop_enabled():
            self.pet.set_enabled(True)               # after everything _update_state() reads exists
        self._poll_activity()
        self.mascot.flash("greeting", 2500)
        if not has_tray:
            self.panel.show_near(None)

    # --- menu ---------------------------------------------------------------
    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction("Abrir panel", self.show_panel)
        menu.addAction("Actualizar lista", self.loader.request)
        self._desktop_action = menu.addAction("", self._toggle_desktop)
        menu.addSeparator()

        colors = menu.addMenu("Color")
        group = QActionGroup(colors)
        for key, (label, *_rest) in sprites.SKINS.items():
            act = colors.addAction(QIcon(render(sprites.frame("idle", 0), key, 32)), label)
            act.setCheckable(True)
            act.setChecked(key == self.mascot.skin)
            act.triggered.connect(partial(self._set_skin, key, None))
            group.addAction(act)

        accessories = menu.addMenu("Accesorio")
        group = QActionGroup(accessories)
        for key, label in sprites.ACCESSORY_LABELS.items():
            act = accessories.addAction(QIcon(render(sprites.frame("idle", 0, key), self.mascot.skin, 32)), label)
            act.setCheckable(True)
            act.setChecked(key == self.mascot.accessory)
            act.triggered.connect(partial(self._set_skin, None, key))
            group.addAction(act)

        sizes = menu.addMenu("Tamaño de la mascota")
        group = QActionGroup(sizes)
        current = self._settings.value("mascot/size", DEFAULT_SIZE, type=int)
        for size, label in SIZES.items():
            act = sizes.addAction(label)
            act.setCheckable(True)
            act.setChecked(size == current)
            act.triggered.connect(partial(self._set_desktop_size, size))
            group.addAction(act)

        animate = menu.addAction("Animar")
        animate.setCheckable(True)
        animate.setChecked(self._settings.value("mascot/animate", True, type=bool))
        animate.toggled.connect(self._set_animated)

        menu.addSeparator()
        self._pet_action = menu.addAction("Modo mascota")
        self._pet_action.setCheckable(True)
        self._pet_action.setChecked(self._settings.value("mascot/petmode", False, type=bool))
        self._pet_action.toggled.connect(self._set_pet_mode)
        self._pet_menu = menu.addMenu("Mascota")
        self._pet_status = self._pet_menu.addAction("")
        self._pet_status.setEnabled(False)
        self._pet_menu.addSeparator()
        self._pet_menu.addAction("Dar de comer  🍪", lambda: self.pet.feed())
        self._pet_menu.addAction("Perseguir el ratón", lambda: self.pet.chase())
        self._clean_action = self._pet_menu.addAction("", lambda: self.pet.clean_all())
        self._pet_menu.aboutToShow.connect(self._update_pet_menu)
        self._pet_menu.setEnabled(self._pet_action.isChecked())

        menu.addSeparator()
        menu.addAction("Salir", self._app.quit)
        self._update_desktop_action()
        return menu

    def _set_skin(self, skin: str | None, accessory: str | None) -> None:
        self.mascot.set_skin(skin, accessory)
        self._settings.setValue("mascot/skin", self.mascot.skin)
        self._settings.setValue("mascot/accessory", self.mascot.accessory)

    def _set_animated(self, on: bool) -> None:
        self.mascot.set_animated(on)
        self._settings.setValue("mascot/animate", on)

    # --- pet mode -----------------------------------------------------------
    def _set_pet_mode(self, on: bool) -> None:
        self._settings.setValue("mascot/petmode", on)
        self._pet_menu.setEnabled(on)
        if on and not self._desktop_enabled():
            self._set_desktop_enabled(True)          # the pet needs to be on the desktop
        self.pet.set_enabled(on)
        self._sync_pet_pause()
        self._update_state()

    def _update_pet_menu(self) -> None:
        needs = self.pet.needs
        self._pet_status.setText(needs.summary() if needs else "Activa el modo mascota")
        self._clean_action.setText(f"Limpiar cacas ({self.pet.poop_count})")
        self._clean_action.setEnabled(self.pet.poop_count > 0)

    def _sync_pet_pause(self) -> None:
        self.pet.set_paused(self.panel.isVisible() or self.chat.busy)

    def _desktop_enabled(self) -> bool:
        return self._settings.value("mascot/desktop", True, type=bool)

    def _update_desktop_action(self) -> None:
        self._desktop_action.setText("Ocultar mascota" if self._desktop_enabled() else "Mostrar mascota")

    def _toggle_desktop(self) -> None:
        self._set_desktop_enabled(not self._desktop_enabled())

    def _set_desktop_enabled(self, on: bool) -> None:
        self._settings.setValue("mascot/desktop", on)
        self.desktop.setVisible(on)
        if not on and self.pet.enabled:              # no pet without a desktop buddy
            self._pet_action.setChecked(False)
        self._update_desktop_action()
        if not on and self.tray:
            self.tray.showMessage("Claude Buddy", "Mascota oculta. Para volver a verla: clic derecho en "
                                  "el icono de la bandeja → Mostrar mascota.", self.mascot.icon(), 5000)

    def _set_desktop_size(self, size: int) -> None:
        self._settings.setValue("mascot/size", size)
        self.desktop.set_size(size)

    # --- tray & panel -------------------------------------------------------
    def _tray_rect(self) -> QRect | None:
        return self.tray.geometry() if self.tray else None

    def _anchor(self) -> QRect | None:
        """Open the panel next to the desktop pet when visible, else next to the tray icon."""
        return self.desktop.frameGeometry() if self.desktop.isVisible() else self._tray_rect()

    def show_panel(self) -> None:
        self.panel.show_near(self._anchor())

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.panel.toggle(self._tray_rect())

    def _on_mascot_changed(self) -> None:
        if self.tray:
            self.tray.setIcon(self.mascot.icon())

    def _on_loaded(self, result: ScanResult) -> None:
        self._sessions = sum(1 for s in result.sessions if s.message_count)
        self.panel.set_result(result)
        self._update_state()

    def _refresh_all(self) -> None:
        self.loader.request()
        if self.panel.current_session:
            self._load_history(self.panel.current_session, refresh=True)

    # --- history ------------------------------------------------------------
    def _load_history(self, session: SessionInfo, refresh: bool = False) -> None:
        self._history_stamp = _file_stamp(session.file)     # taken before reading: no change is missed
        self._history_checked = time.monotonic()
        self.history.request(session, refresh)

    # --- terminal (phase 5) --------------------------------------------------
    def _open_terminal(self, session: SessionInfo) -> None:
        # One process per session: drop our own SDK connection to it first
        if not self.chat.release(session.session_id):
            self.panel.show_message("Espera a que Claude termine de responder antes de abrir la terminal.", 6000)
            return
        try:
            open_in_terminal(session)
        except TerminalError as exc:
            self.panel.show_message(f"⚠ {exc}", 8000)
            return
        self.panel.show_message("Sesión abierta en la terminal. No escribas aquí a la vez.", 6000)

    # --- chat ---------------------------------------------------------------
    def _chat_send(self, session: SessionInfo, text: str, mode: str) -> None:
        self.chat.send(session, text, mode)

    def _on_chat_event(self, ev: ChatEvent) -> None:
        self.panel.on_chat_event(ev)
        if ev.kind == "busy":
            self._chat_activity = "thinking" if ev.data["busy"] else None
            self._sync_pet_pause()
            if not ev.data["busy"]:
                # our own writes to the session file are not "someone else working"
                self._ignore_activity_until = time.time() + WORKING_SECS + 2
                session = self.panel.current_session
                if session:   # reconcile the live view with what Claude Code saved
                    QTimer.singleShot(1500, lambda s=session: self._load_history(s, refresh=True))
        elif ev.kind == "activity":
            self._chat_activity = ev.text
        elif ev.kind == "text_delta":
            self._chat_activity = "writing"
        elif ev.kind == "permission" and not self.panel.isVisible() and self.tray:
            self.tray.showMessage("Claude necesita permiso", ev.text, self.mascot.icon(), 8000)
        elif ev.kind == "result":
            self.mascot.flash("error" if ev.data.get("is_error") else "done", 4000)
        elif ev.kind == "error":
            self.mascot.flash("error", 5000)
        elif ev.kind == "session" and self.panel.current_session:
            old = self.panel.current_session
            self.panel.update_current_session(
                replace(old, session_id=ev.text, file=old.file.with_name(f"{ev.text}.jsonl")))
        self._update_state()

    def _follow_open_history(self) -> None:
        """Reload the open history when its file changes (session still running elsewhere)."""
        session = self.panel.current_session
        if (session is None or not self.panel.isVisible() or self.history.busy or self.chat.busy
                or time.monotonic() - self._history_checked < HISTORY_REFRESH_SECS):
            return
        if _file_stamp(session.file) != self._history_stamp:
            self._load_history(session, refresh=True)

    # --- activity → mascot state -------------------------------------------
    def _poll_activity(self) -> None:
        mtime = newest_mtime()
        if mtime is not None and (self._last_write is None or mtime > self._last_write):
            first = self._last_write is None
            self._last_write = mtime
            if not first and self.panel.isVisible():
                self.loader.request()           # keep the open list up to date
        self._follow_open_history()
        self._update_state()

    def _update_state(self) -> None:
        now = time.time()
        age = None if self._last_write is None else now - self._last_write
        working = age is not None and age < WORKING_SECS and now > self._ignore_activity_until
        if self.chat.busy and self._chat_activity:
            state = self._chat_activity                 # our own chat drives the buddy
            working = False
        elif working:
            state, self._was_working = "writing", True
        elif self._was_working:
            self._was_working, self._done_until = False, now + DONE_SECS
            state = "done"
        elif now < self._done_until:
            state = "done"
        elif self.loader.busy or self.history.busy:
            state = "reading"
        elif age is None or age > SLEEP_SECS:
            state = "asleep"
        else:
            state = "idle"
        if self.pet.enabled and not (self.chat.busy and self._chat_activity):
            state = self.pet.sprite_state or state      # pet mode: its own life, unless we are chatting
        self.mascot.set_state(state)

        activity = "Claude está trabajando…" if working else ""
        self.panel.set_activity(activity)
        if self.tray:
            self.tray.setToolTip("\n".join(filter(None, [f"Claude Buddy — {self._sessions} sesiones", activity])))

    def shutdown(self) -> None:
        self._activity_timer.stop()
        self.pet.shutdown()
        self.chat.close()
        self.loader.shutdown()
        self.history.shutdown()
        self.desktop.hide()
        if self.tray:
            self.tray.hide()


# --- single instance -------------------------------------------------------
def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # no user env vars available
        user = "user"
    return "claude-buddy-" + re.sub(r"\W", "_", user)


def _notify_running_instance(name: str) -> bool:
    """If another Claude Buddy is running, ask it to show its panel and return True."""
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(300):
        return False
    sock.write(b"show")
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def _listen(name: str, on_show) -> QLocalServer:
    QLocalServer.removeServer(name)            # clears a stale socket after a crash (Unix)
    server = QLocalServer()
    server.listen(name)

    def accept() -> None:
        while (conn := server.nextPendingConnection()) is not None:
            conn.disconnected.connect(conn.deleteLater)
            conn.close()
            on_show()

    server.newConnection.connect(accept)
    return server


def _set_windows_app_id() -> None:
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ClaudeBuddy.App")
        except (AttributeError, OSError):
            pass


def main() -> int:
    QApplication.setOrganizationName(APP_ID)
    QApplication.setApplicationName(APP_ID)
    QApplication.setApplicationDisplayName("Claude Buddy")
    _set_windows_app_id()
    hide_child_consoles()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    log_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "logs"
    try:
        setup_logging(log_dir)
    except OSError:
        pass                                   # logging is best effort
    logging.getLogger("claude_buddy").info("Claude Buddy %s starting", __version__)

    if "--diagnose" in sys.argv:
        from .diagnose import run
        ok, lines = run()
        if "--no-dialog" not in sys.argv:
            box = QMessageBox.information if ok else QMessageBox.warning
            box(None, "Claude Buddy · diagnóstico", "\n\n".join(lines))
        return 0 if ok else 1

    name = _server_name()
    if _notify_running_instance(name):
        return 0
    buddy = Buddy(app)
    server = _listen(name, buddy.show_panel)
    app.aboutToQuit.connect(buddy.shutdown)
    code = app.exec()
    server.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
