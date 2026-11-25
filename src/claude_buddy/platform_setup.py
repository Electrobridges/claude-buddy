"""Process-wide setup for the GUI app: log file, crash logging, hidden child consoles on Windows."""

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("claude_buddy")


def setup_logging(log_dir: Path) -> Path:
    """Log to <log_dir>/buddy.log (the packaged app has no console to show errors)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "buddy.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    def excepthook(exc_type, exc, tb) -> None:
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = excepthook
    return path


def hide_child_consoles() -> None:
    """On Windows, start console children (claude.exe, shells) without opening a console window.

    claude-agent-sdk spawns the CLI without CREATE_NO_WINDOW; from a windowed app that would pop
    up a terminal for every chat. VS Code's extension hides them the same way.
    """
    if sys.platform != "win32" or getattr(subprocess.Popen.__init__, "_buddy_patched", False):
        return
    original = subprocess.Popen.__init__

    def init(self, *args, **kwargs):
        # anyio passes creationflags=0 explicitly, so treat 0 as "not set";
        # callers that want a window (opening a terminal) pass non-zero flags
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        original(self, *args, **kwargs)

    init._buddy_patched = True  # type: ignore[attr-defined]
    subprocess.Popen.__init__ = init  # type: ignore[method-assign]
