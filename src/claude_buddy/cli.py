"""Phase 1: list local Claude Code sessions in the console."""

import argparse
import shutil
import sys
from pathlib import Path

from .models import SessionInfo
from .parser import one_line
from .scanner import scan_sessions

_ORIGINS = {"claude-vscode": "vscode", "claude-desktop": "desktop"}


def _fit(text: str, width: int) -> str:
    return one_line(text, width).ljust(width)


def format_table(sessions: list[SessionInfo], total_width: int) -> list[str]:
    proj_w = min(24, max([8] + [len(s.project_name) for s in sessions]))
    fixed = 16 + 5 + 7 + proj_w + 8 + 5 * 2      # columns + separators
    title_w = max(20, total_width - fixed - 1)
    header = f"{'Última actividad':<16}  {'Msgs':>5}  {'Origen':<7}  {_fit('Proyecto', proj_w)}  {'ID':<8}  Título"
    lines = [header, "-" * min(total_width - 1, fixed + title_w)]
    for s in sessions:
        when = s.last_activity.astimezone().strftime("%Y-%m-%d %H:%M")
        origin = _ORIGINS.get(s.entrypoint or "", s.entrypoint or "?")
        lines.append(
            f"{when:<16}  {s.message_count:>5}  {_fit(origin, 7)}  {_fit(s.project_name, proj_w)}  "
            f"{s.session_id[:8]}  {one_line(s.title, title_w)}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="claude-buddy-list",
                                 description="Lista las sesiones locales de Claude Code.")
    ap.add_argument("-n", "--limit", type=int, default=0, help="máximo de sesiones a mostrar (0 = todas)")
    ap.add_argument("--dir", type=Path, help="carpeta de proyectos (por defecto ~/.claude/projects)")
    ap.add_argument("-a", "--all", action="store_true", help="incluir sesiones vacías (0 mensajes)")
    args = ap.parse_args(argv)

    # Never crash on characters the console code page cannot show
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    result = scan_sessions(args.dir)
    for warning in result.warnings:
        print(f"aviso: {warning}", file=sys.stderr)

    sessions = result.sessions if args.all else [s for s in result.sessions if s.message_count]
    if not sessions:
        print("No se encontraron sesiones.")
        return 0

    shown = sessions[: args.limit] if args.limit > 0 else sessions
    width = shutil.get_terminal_size((140, 24)).columns
    print("\n".join(format_table(shown, width)))
    projects = len({s.project_key for s in sessions})
    hidden = len(result.sessions) - len(sessions)
    print(f"\n{len(sessions)} sesiones en {projects} proyectos"
          + (f" (mostrando {len(shown)})" if len(shown) < len(sessions) else "")
          + (f"; {hidden} vacías ocultas (usa --all)" if hidden else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
