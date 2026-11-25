"""Open `claude --resume <id>` in a new terminal window, in the session's project folder."""

import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .chat import find_claude_cli
from .models import SessionInfo

CREATE_NEW_CONSOLE = 0x00000010
DETACHED_PROCESS = 0x00000008


class TerminalError(RuntimeError):
    pass


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _applescript_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_command(session_id: str, cwd: str, cli: str, platform: str = sys.platform,
                  which: Callable[[str], str | None] = shutil.which) -> tuple[list[str], dict[str, Any]]:
    """Return (argv, Popen kwargs) that open a terminal running the resumed session."""
    if platform == "win32":
        if wt := which("wt"):                         # Windows Terminal
            return [wt, "-d", cwd, cli, "--resume", session_id], {"creationflags": DETACHED_PROCESS}
        shell = which("pwsh") or which("powershell") or "powershell.exe"
        command = f"& {_ps_quote(cli)} --resume {_ps_quote(session_id)}"
        return [shell, "-NoExit", "-Command", command], {"cwd": cwd, "creationflags": CREATE_NEW_CONSOLE}

    inner = f"cd {shlex.quote(cwd)} && {shlex.quote(cli)} --resume {shlex.quote(session_id)}"
    if platform == "darwin":
        script = f"tell application \"Terminal\" to do script {_applescript_quote(inner)}"
        return ["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'], {}

    keep_open = f'{inner}; exec "${{SHELL:-bash}}"'           # stay in the shell after claude exits
    candidates = [
        ("gnome-terminal", ["--", "bash", "-lc", keep_open]),
        ("konsole", ["-e", "bash", "-lc", keep_open]),
        ("xfce4-terminal", ["-x", "bash", "-lc", keep_open]),
        ("kitty", ["bash", "-lc", keep_open]),
        ("alacritty", ["-e", "bash", "-lc", keep_open]),
        ("wezterm", ["start", "--", "bash", "-lc", keep_open]),
        ("x-terminal-emulator", ["-e", "bash", "-lc", keep_open]),
        ("xterm", ["-e", "bash", "-lc", keep_open]),
    ]
    for name, args in candidates:
        if path := which(name):
            return [path, *args], {"cwd": cwd}
    raise TerminalError("No se encontró ningún emulador de terminal (gnome-terminal, konsole, xterm…).")


def open_in_terminal(session: SessionInfo) -> None:
    if not session.cwd or not Path(session.cwd).is_dir():
        raise TerminalError(f"La carpeta del proyecto ya no existe: {session.cwd or '(desconocida)'}")
    argv, kwargs = build_command(session.session_id, session.cwd, find_claude_cli() or "claude")
    try:
        subprocess.Popen(argv, **kwargs)
    except OSError as exc:
        raise TerminalError(f"No se pudo abrir la terminal: {exc}") from exc
