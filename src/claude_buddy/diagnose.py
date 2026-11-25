"""`ClaudeBuddy.exe --diagnose`: check the pieces the app depends on, without sending any message."""

import asyncio
import logging
import subprocess
import sys
import tempfile

from . import __version__
from .chat import find_claude_cli
from .paths import projects_dir
from .scanner import scan_sessions

log = logging.getLogger(__name__)


async def _sdk_handshake(cli: str | None) -> str:
    """Start Claude Code through the SDK and read its init info (no prompt is sent)."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    with tempfile.TemporaryDirectory() as tmp:
        client = ClaudeSDKClient(ClaudeAgentOptions(cli_path=cli, cwd=tmp, setting_sources=[]))
        await asyncio.wait_for(client.connect(), 60)
        try:
            info = await client.get_server_info() or {}
        finally:
            await client.disconnect()
    return f"ok ({len(info.get('commands', []))} comandos disponibles)"


def run() -> tuple[bool, list[str]]:
    lines = [f"Claude Buddy {__version__} · Python {sys.version.split()[0]} · "
             f"{'empaquetado' if getattr(sys, 'frozen', False) else 'desde código fuente'}"]
    ok = True

    cli = find_claude_cli()
    if cli:
        try:
            out = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=30)
            lines.append(f"✔ Claude Code: {cli} — {out.stdout.strip() or out.stderr.strip()}")
        except (OSError, subprocess.SubprocessError) as exc:
            ok = False
            lines.append(f"✘ Claude Code encontrado pero no se puede ejecutar: {exc}")
    else:
        ok = False
        lines.append("✘ Claude Code no encontrado (comando 'claude'). El chat no funcionará.")

    result = scan_sessions()
    lines.append(f"{'✔' if result.sessions else '•'} Sesiones en {projects_dir()}: {len(result.sessions)}"
                 + (f" ({len(result.warnings)} avisos)" if result.warnings else ""))

    if cli:
        try:
            lines.append(f"✔ SDK ↔ Claude Code: {asyncio.run(_sdk_handshake(cli))}")
        except Exception as exc:  # report whatever broke
            ok = False
            lines.append(f"✘ SDK ↔ Claude Code: {type(exc).__name__}: {exc}")

    for line in lines:
        log.info("diagnose: %s", line)
    return ok, lines
