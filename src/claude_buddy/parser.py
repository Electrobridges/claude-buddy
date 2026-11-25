"""Parse one Claude Code session file. Format notes: docs/formato-jsonl.md."""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import SessionInfo

TITLE_MAX = 120
NO_TITLE = "(sin título)"

# Text blocks injected as context by Claude Code / the IDE, never typed by the user
_CONTEXT_TAGS = (
    "ide_opened_file", "ide_selection", "system-reminder", "task-notification",
    "local-command-stdout", "local-command-stderr", "local-command-caveat",
    "bash-stdout", "bash-stderr",
)
_CONTEXT_RE = re.compile(r"^\s*<(?:" + "|".join(map(re.escape, _CONTEXT_TAGS)) + r")\b")
_PASTED_RE = re.compile(r"<pasted_content\b[^>]*>(.*?)</pasted_content\b[^>]*>", re.DOTALL)
_COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
_COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
_BASH_INPUT_RE = re.compile(r"<bash-input>(.*?)</bash-input>", re.DOTALL)
_IMAGE_REF_RE = re.compile(r"\[Image #\d+\]\s*")
INTERRUPTED = "[Request interrupted by user"      # synthetic marker written by Claude Code

Record = dict[str, Any]


def _blocks(content: Any) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def extract_prompt(record: Record) -> tuple[str, bool] | None:
    """Return (visible text, is_slash_command) for a real user prompt, else None.

    Image-only prompts return ("", False): they count as messages but have no text.
    """
    if (record.get("type") != "user" or record.get("isMeta") or record.get("isSidechain")
            or record.get("isCompactSummary") or record.get("toolUseResult") is not None):
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    blocks = _blocks(message.get("content"))
    if not blocks or any(b.get("type") == "tool_result" for b in blocks):
        return None

    texts: list[str] = []
    has_media = False
    for b in blocks:
        kind = b.get("type")
        if kind == "text":
            text = b.get("text")
            if isinstance(text, str) and not _CONTEXT_RE.match(text) and not text.startswith(INTERRUPTED):
                texts.append(text)
        elif kind in ("image", "document"):
            has_media = True

    raw = _IMAGE_REF_RE.sub("", "\n".join(texts)).strip()
    if not raw:
        return ("", False) if has_media else None
    if cmd := _COMMAND_NAME_RE.search(raw):
        args = _COMMAND_ARGS_RE.search(raw)
        return f"{cmd.group(1).strip()} {args.group(1).strip() if args else ''}".strip(), True
    if bash := _BASH_INPUT_RE.search(raw):
        return f"! {bash.group(1).strip()}", False
    return _PASTED_RE.sub(lambda m: m.group(1), raw).strip(), False


def assistant_reply_id(record: Record) -> str | None:
    """Return the API message id if this record carries visible assistant text."""
    if record.get("type") != "assistant" or record.get("isSidechain") or record.get("isApiErrorMessage"):
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    for b in _blocks(message.get("content")):
        if b.get("type") == "text" and str(b.get("text", "")).strip():
            return message.get("id") or record.get("uuid") or ""
    return None


def one_line(text: str, limit: int = TITLE_MAX) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _sidecar_title(path: Path) -> str | None:
    """Title stored in <session-id>/custom-title.json (Claude Desktop sessions)."""
    sidecar = path.with_suffix("") / "custom-title.json"
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8")).get("customTitle")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and value.strip() else None


def parse_session(path: Path, warn: Callable[[str], None] | None = None) -> SessionInfo:
    """Read a session file line by line. Corrupt lines are skipped and reported via `warn`.

    Raises OSError if the file cannot be read at all.
    """
    bad_lines = 0
    cwd = entrypoint = None
    last: datetime | None = None
    first_prompt = first_command = None
    titles: dict[str, str] = {}          # record type -> latest title of that kind
    user_count = 0
    reply_ids: set[str] = set()

    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            if not isinstance(rec, dict):
                bad_lines += 1
                continue

            if cwd is None and isinstance(rec.get("cwd"), str):
                cwd = rec["cwd"]
            if entrypoint is None and isinstance(rec.get("entrypoint"), str):
                entrypoint = rec["entrypoint"]
            if (ts := _parse_ts(rec.get("timestamp"))) and (last is None or ts > last):
                last = ts

            kind = rec.get("type")
            if kind == "custom-title" and isinstance(rec.get("customTitle"), str):
                titles[kind] = rec["customTitle"]
            elif kind == "ai-title" and isinstance(rec.get("aiTitle"), str):
                titles[kind] = rec["aiTitle"]
            elif kind == "summary" and isinstance(rec.get("summary"), str):
                titles[kind] = rec["summary"]
            elif (prompt := extract_prompt(rec)) is not None:
                user_count += 1
                text, is_command = prompt
                if text and is_command and first_command is None:
                    first_command = text
                elif text and not is_command and first_prompt is None:
                    first_prompt = text
            elif (reply := assistant_reply_id(rec)) is not None:
                reply_ids.add(reply)

    if bad_lines and warn:
        warn(f"{path.name}: {bad_lines} línea(s) ilegibles ignoradas")

    if last is None:
        last = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    # Plain prompts beat slash commands (sessions often start with /clear, /model...)
    title = (first_prompt or first_command or titles.get("custom-title") or _sidecar_title(path)
             or titles.get("ai-title") or titles.get("summary") or NO_TITLE)

    return SessionInfo(
        session_id=path.stem,
        file=path,
        project_folder=path.parent.name,
        cwd=cwd,
        title=one_line(title),
        last_activity=last,
        message_count=user_count + len(reply_ids),
        entrypoint=entrypoint,
    )
