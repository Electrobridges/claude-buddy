"""Continue a Claude Code session with claude-agent-sdk (resume + streaming), off the GUI thread.

The engine owns an asyncio loop in a background thread and reports everything through a
single `emit(ChatEvent)` callback, so it has no Qt dependency and can be tested with a fake client.
"""

import asyncio
import logging
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import SessionInfo
from .transcript import tool_summary

log = logging.getLogger(__name__)

PERMISSION_MODES = {"default": "Preguntar", "acceptEdits": "Aceptar ediciones", "plan": "Solo planificar"}

# Which buddy animation fits each tool
_TOOL_ACTIVITY = {
    "Read": "reading", "NotebookRead": "reading",
    "Grep": "searching", "Glob": "searching", "WebSearch": "searching", "WebFetch": "searching",
    "ToolSearch": "searching",
    "Bash": "running", "PowerShell": "running",
    "Edit": "writing", "MultiEdit": "writing", "Write": "writing", "NotebookEdit": "writing",
    "Agent": "thinking", "Task": "thinking",
}


def tool_activity(name: str) -> str:
    return _TOOL_ACTIVITY.get(name, "running")


@dataclass(frozen=True)
class ChatEvent:
    """kind: busy | activity | text_delta | text | tool | tool_error | permission | result | error | session"""
    kind: str
    session_id: str
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def find_claude_cli() -> str | None:
    """Prefer the user's installed Claude Code (same version and login as their sessions).

    Also checks the native installer's locations: apps started from the Start menu or at
    login may not see the user's full PATH.
    """
    if found := shutil.which("claude"):
        return found
    home = Path.home()
    for candidate in (home / ".local" / "bin" / "claude.exe", home / ".local" / "bin" / "claude",
                      home / ".claude" / "local" / "claude.exe", home / ".claude" / "local" / "claude"):
        if candidate.is_file():
            return str(candidate)
    return None


class ChatEngine:
    """One live SDK client at a time, bound to the session being chatted with."""

    def __init__(self, emit: Callable[[ChatEvent], None], client_factory: Callable[..., Any] | None = None,
                 options_factory: Callable[..., Any] | None = None) -> None:
        self._emit = emit
        self._client_factory = client_factory
        self._options_factory = options_factory
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="buddy-chat", daemon=True)
        self._thread.start()
        self._client: Any = None
        self._client_session: str | None = None       # id reported in events
        self._bound: tuple[str, str | None] | None = None   # (session id, cwd) the live client serves
        self._cwd: str | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._busy = False

    # --- public API (any thread) -------------------------------------------
    @property
    def busy(self) -> bool:
        return self._busy

    def send(self, session: SessionInfo, prompt: str, mode: str = "default") -> None:
        asyncio.run_coroutine_threadsafe(self._send(session, prompt, mode), self._loop)

    def interrupt(self) -> None:
        asyncio.run_coroutine_threadsafe(self._interrupt(), self._loop)

    def release(self, session_id: str) -> bool:
        """Close the live connection to this session (e.g. before resuming it in a terminal).
        Returns False if a reply is still in progress."""
        if self._busy and self._bound and self._bound[0] == session_id:
            return False

        async def _release() -> None:
            if self._bound and self._bound[0] == session_id and not self._busy:
                await self._disconnect()

        asyncio.run_coroutine_threadsafe(_release(), self._loop)
        return True

    def set_mode(self, mode: str) -> None:
        asyncio.run_coroutine_threadsafe(self._set_mode(mode), self._loop)

    def answer_permission(self, request_id: str, allow: bool) -> None:
        def resolve() -> None:
            fut = self._pending.pop(request_id, None)
            if fut and not fut.done():
                fut.set_result(allow)
        self._loop.call_soon_threadsafe(resolve)

    def close(self, timeout: float = 5.0) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop).result(timeout)
        except Exception:  # shutting down anyway
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    # --- internals (event loop thread) --------------------------------------
    def _event(self, kind: str, text: str = "", **data: Any) -> None:
        self._emit(ChatEvent(kind, self._client_session or "", text, data))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._event("busy", busy=busy)

    def _make_client(self, session: SessionInfo, mode: str) -> Any:
        if self._client_factory is None:
            from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
            self._client_factory, self._options_factory = ClaudeSDKClient, ClaudeAgentOptions
        options = self._options_factory(
            resume=session.session_id,           # same session id: continues the same conversation
            cwd=session.cwd,
            include_partial_messages=True,
            permission_mode=mode,
            can_use_tool=self._can_use_tool,
            cli_path=find_claude_cli(),          # None -> SDK's bundled CLI (not shipped in the installer)
            stderr=lambda line: log.info("claude: %s", line.rstrip()),
        )
        return self._client_factory(options)

    async def _send(self, session: SessionInfo, prompt: str, mode: str) -> None:
        if self._busy:
            return
        self._client_session = session.session_id
        self._set_busy(True)
        self._event("activity", "thinking")
        try:
            if not session.cwd or not Path(session.cwd).is_dir():
                raise RuntimeError(f"La carpeta del proyecto ya no existe: {session.cwd or '(desconocida)'}")
            if self._client is None or self._bound != (session.session_id, session.cwd):
                await self._disconnect()
                self._cwd = session.cwd
                self._client = self._make_client(session, mode)
                await self._client.connect()
                self._bound = (session.session_id, session.cwd)
            await self._client.query(prompt)
            async for message in self._client.receive_response():
                self._handle(message)
        except Exception as exc:  # report and reset: next send reconnects
            self._event("error", _friendly_error(exc))
            await self._disconnect()
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_result(False)
            self._pending.clear()
            self._set_busy(False)

    async def _interrupt(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_result(False)
        if self._client is not None and self._busy:
            try:
                await self._client.interrupt()
            except Exception as exc:
                self._event("error", _friendly_error(exc))

    async def _set_mode(self, mode: str) -> None:
        if self._client is not None and not self._busy:
            try:
                await self._client.set_permission_mode(mode)
            except Exception:  # takes effect on next connect anyway
                await self._disconnect()

    async def _disconnect(self) -> None:
        client, self._client = self._client, None
        self._bound = None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # process may already be gone
                pass

    async def _can_use_tool(self, tool_name: str, tool_input: dict[str, Any], context: Any) -> Any:
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
        request_id = uuid.uuid4().hex
        fut = self._loop.create_future()
        self._pending[request_id] = fut
        self._event("activity", "waiting")
        self._event("permission", tool_summary(tool_name, tool_input, self._cwd), id=request_id, tool=tool_name)
        allowed = await fut
        self._event("activity", tool_activity(tool_name) if allowed else "thinking")
        if allowed:
            return PermissionResultAllow()
        return PermissionResultDeny(message="El usuario denegó este permiso desde Claude Buddy.")

    def _handle(self, message: Any) -> None:
        kind = type(message).__name__
        if getattr(message, "parent_tool_use_id", None):        # subagent internals: not shown
            return
        if kind == "StreamEvent":
            event = message.event or {}
            etype = event.get("type")
            if etype == "content_block_start":
                block = event.get("content_block") or {}
                if block.get("type") == "tool_use":
                    self._event("activity", tool_activity(block.get("name", "")))
                elif block.get("type") == "thinking":
                    self._event("activity", "thinking")
                elif block.get("type") == "text":
                    self._event("activity", "writing")
            elif etype == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    self._event("text_delta", delta["text"])
        elif kind == "AssistantMessage":
            for block in message.content:
                bkind = type(block).__name__
                if bkind == "TextBlock" and block.text.strip():
                    self._event("text", block.text)
                elif bkind == "ToolUseBlock":
                    self._event("tool", tool_summary(block.name, block.input, self._cwd), name=block.name)
            if getattr(message, "error", None):
                self._event("error", f"Error de la API: {message.error}")
        elif kind == "UserMessage" and isinstance(message.content, list):
            for block in message.content:
                if type(block).__name__ == "ToolResultBlock" and getattr(block, "is_error", False):
                    self._event("tool_error", _first_line(block.content))
        elif kind == "ResultMessage":
            if message.session_id and message.session_id != self._client_session:
                self._client_session = message.session_id       # CLI forked: follow the new id
                self._event("session", message.session_id)
            self._event("result", (message.result or "") if message.is_error else "",
                        is_error=message.is_error, cost=message.total_cost_usd, subtype=message.subtype)


def _first_line(content: Any) -> str:
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    text = " ".join(str(content or "error").split())
    return text[:160] + ("…" if len(text) > 160 else "")


def _friendly_error(exc: Exception) -> str:
    name = type(exc).__name__
    if name == "CLINotFoundError":
        return "No se encontró Claude Code. Instálalo o comprueba que el comando 'claude' está en el PATH."
    if name == "ProcessError":
        return f"Claude Code terminó con un error: {exc}"
    return str(exc) or name
