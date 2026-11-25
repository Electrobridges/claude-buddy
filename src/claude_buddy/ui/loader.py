"""Runs SessionIndex.refresh() off the GUI thread."""

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot

from ..models import SessionInfo
from ..scanner import ScanResult, SessionIndex
from ..transcript import Transcript, load_transcript


class IndexLoader(QObject):
    loaded = Signal(object)        # ScanResult
    busy_changed = Signal(bool)
    _finished = Signal(object)     # emitted from the worker thread

    def __init__(self, root: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._index = SessionIndex(root)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="buddy-scan")
        self._busy = False
        self._pending = False
        self._finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)

    @property
    def busy(self) -> bool:
        return self._busy

    def request(self) -> None:
        """Start a refresh; if one is running, queue exactly one more."""
        if self._busy:
            self._pending = True
            return
        self._busy = True
        self.busy_changed.emit(True)
        self._pool.submit(self._run)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _run(self) -> None:
        try:
            result = self._index.refresh()
        except Exception as exc:  # never let the worker die silently
            result = ScanResult(warnings=[f"Error inesperado al leer las sesiones: {exc}"])
        self._finished.emit(result)

    @Slot(object)
    def _on_finished(self, result: ScanResult) -> None:
        self._busy = False
        self.busy_changed.emit(False)
        self.loaded.emit(result)
        if self._pending:
            self._pending = False
            self.request()


class TranscriptLoader(QObject):
    """Loads one session's history off the GUI thread; only the latest request is delivered."""

    loaded = Signal(object, object, bool)        # SessionInfo, Transcript, is_refresh
    busy_changed = Signal(bool)                  # only for first loads (refreshes are silent)
    _finished = Signal(int, object, object, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="buddy-history")
        self._token = 0
        self._future: Future | None = None
        self._busy = False
        self._finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)

    @property
    def busy(self) -> bool:
        return self._busy

    def request(self, session: SessionInfo, refresh: bool = False) -> None:
        self._token += 1
        if self._future:
            self._future.cancel()                # drop a queued, now stale, request
        if not refresh and not self._busy:
            self._busy = True
            self.busy_changed.emit(True)
        self._future = self._pool.submit(self._run, self._token, session, refresh)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _run(self, token: int, session: SessionInfo, refresh: bool) -> None:
        try:
            transcript = load_transcript(session.file)
        except Exception as exc:  # unreadable file must not kill the worker
            transcript = Transcript(warnings=[f"No se pudo leer el historial: {exc}"])
        self._finished.emit(token, session, transcript, refresh)

    @Slot(int, object, object, bool)
    def _on_finished(self, token: int, session: SessionInfo, transcript: Transcript, refresh: bool) -> None:
        if token != self._token:
            return
        if self._busy:
            self._busy = False
            self.busy_changed.emit(False)
        self.loaded.emit(session, transcript, refresh)
