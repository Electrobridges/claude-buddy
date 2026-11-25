"""Discover and parse all sessions under ~/.claude/projects (read-only)."""

from dataclasses import dataclass, field
from pathlib import Path

from .models import SessionInfo
from .parser import parse_session
from .paths import projects_dir


@dataclass
class ScanResult:
    sessions: list[SessionInfo] = field(default_factory=list)   # newest first
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Entry:
    stamp: tuple[int, int]          # (mtime_ns, size)
    session: SessionInfo | None
    warnings: list[str]


class SessionIndex:
    """Incremental scanner: only re-parses files whose mtime or size changed."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self._cache: dict[Path, _Entry] = {}

    def refresh(self) -> ScanResult:
        """Problems become warnings, never exceptions."""
        root = self.root or projects_dir()
        result = ScanResult()
        if not root.is_dir():
            self._cache.clear()
            result.warnings.append(f"No existe la carpeta de sesiones: {root}")
            return result

        try:
            folders = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError as exc:
            result.warnings.append(f"No se pudo leer {root}: {exc}")
            return result

        seen: set[Path] = set()
        for folder in folders:
            try:
                files = sorted(folder.glob("*.jsonl"))     # top level only: skips subagents/
            except OSError as exc:
                result.warnings.append(f"No se pudo leer {folder}: {exc}")
                continue
            for file in files:
                seen.add(file)
                entry = self._load(file)
                result.warnings.extend(entry.warnings)
                if entry.session:
                    result.sessions.append(entry.session)

        for gone in self._cache.keys() - seen:
            del self._cache[gone]
        result.sessions.sort(key=lambda s: s.last_activity, reverse=True)
        return result

    def _load(self, file: Path) -> _Entry:
        try:
            st = file.stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError as exc:
            return _Entry((0, 0), None, [f"{file.name}: no se pudo leer ({exc})"])
        cached = self._cache.get(file)
        if cached and cached.stamp == stamp:
            return cached
        warnings: list[str] = []
        try:
            session = parse_session(file, warn=warnings.append)
        except Exception as exc:  # one bad file must never stop the scan
            session = None
            warnings.append(f"{file.name}: no se pudo procesar ({exc})")
        entry = _Entry(stamp, session, warnings)
        self._cache[file] = entry
        return entry


def scan_sessions(root: Path | None = None) -> ScanResult:
    return SessionIndex(root).refresh()


def newest_mtime(root: Path | None = None) -> float | None:
    """Most recent modification time of any session file (cheap: stat only)."""
    root = root or projects_dir()
    newest = None
    try:
        for file in root.glob("*/*.jsonl"):
            try:
                mtime = file.stat().st_mtime
            except OSError:
                continue
            newest = mtime if newest is None else max(newest, mtime)
    except OSError:
        return None
    return newest
