"""Phase 5: command used to resume a session in a terminal, per platform."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_buddy.models import SessionInfo
from claude_buddy.terminal import CREATE_NEW_CONSOLE, TerminalError, build_command, open_in_terminal

SID = "abc-123"


def which_from(*names: str):
    return lambda name: f"/bin/{name}" if name in names else None


def test_windows_prefers_windows_terminal():
    argv, kw = build_command(SID, r"C:\dev\mi proyecto", r"C:\bin\claude.exe", "win32", which_from("wt"))
    assert argv == ["/bin/wt", "-d", r"C:\dev\mi proyecto", r"C:\bin\claude.exe", "--resume", SID]
    assert kw["creationflags"]                                  # never 0: no hidden-console patch


def test_windows_falls_back_to_powershell():
    argv, kw = build_command(SID, r"C:\dev\x", r"C:\Program Files\it's\claude.exe", "win32", which_from("powershell"))
    assert argv[:3] == ["/bin/powershell", "-NoExit", "-Command"]
    assert argv[3] == "& 'C:\\Program Files\\it''s\\claude.exe' --resume 'abc-123'"
    assert kw == {"cwd": r"C:\dev\x", "creationflags": CREATE_NEW_CONSOLE}


def test_macos_uses_terminal_app():
    argv, _ = build_command(SID, "/Users/a/my dir", "/usr/local/bin/claude", "darwin", which_from())
    assert argv[0] == "osascript"
    assert "cd '/Users/a/my dir' && /usr/local/bin/claude --resume abc-123" in argv[2]


def test_linux_picks_first_available_terminal():
    argv, kw = build_command(SID, "/home/a/p", "claude", "linux", which_from("konsole", "xterm"))
    assert argv[0] == "/bin/konsole" and argv[1:4] == ["-e", "bash", "-lc"]
    assert argv[4].startswith("cd /home/a/p && claude --resume abc-123")
    assert kw == {"cwd": "/home/a/p"}
    with pytest.raises(TerminalError):
        build_command(SID, "/home/a/p", "claude", "linux", which_from())


def test_missing_project_folder(tmp_path: Path):
    s = SessionInfo(SID, tmp_path / "x.jsonl", "f", str(tmp_path / "gone"), "t", datetime.now(UTC), 1, "cli")
    with pytest.raises(TerminalError, match="ya no existe"):
        open_in_terminal(s)
