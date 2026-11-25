"""Turn a session .jsonl into a readable conversation (format: docs/formato-jsonl.md)."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .parser import INTERRUPTED, Record, _blocks, _parse_ts, extract_prompt, one_line

MAX_TEXT = 20_000          # longer messages are cut in the viewer

# Most useful input field to summarise each tool call
_TOOL_KEYS = {
    "Bash": "command", "PowerShell": "command", "Read": "file_path", "Edit": "file_path",
    "MultiEdit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path",
    "Grep": "pattern", "Glob": "pattern", "WebFetch": "url", "WebSearch": "query",
    "Agent": "description", "Task": "description", "Skill": "skill",
}
_FALLBACK_KEYS = ("description", "command", "file_path", "path", "pattern", "url", "query", "prompt")


@dataclass(frozen=True, slots=True)
class Entry:
    kind: str                      # user | command | assistant | tool | error | notice
    text: str
    timestamp: datetime | None = None


@dataclass
class Transcript:
    entries: list[Entry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _cut(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n\n… (mensaje recortado)"


def tool_summary(name: str, tool_input: Any, cwd: str | None = None) -> str:
    """'Bash · git status', 'Read · src/app.py' … (paths shown relative to the project)."""
    value = None
    if isinstance(tool_input, dict):
        key = _TOOL_KEYS.get(name)
        value = tool_input.get(key) if key else None
        if not isinstance(value, str):
            value = next((tool_input[k] for k in _FALLBACK_KEYS if isinstance(tool_input.get(k), str)), None)
    if value and cwd:
        base = cwd.rstrip("\\/").replace("\\", "/").lower()
        unified = value.replace("\\", "/")
        if unified.lower().startswith(base + "/"):          # either separator, any case
            value = value[len(base) + 1:]
    if name == "TodoWrite":
        value = "lista de tareas"
    pretty = name.removeprefix("mcp__").replace("__", " · ") if name.startswith("mcp__") else name
    return f"{pretty} · {one_line(value, 100)}" if value else pretty


def _tool_error_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return one_line(str(content or "error"), 160)


def _main_chain(records: list[Record]) -> set[str]:
    """uuids on the path from the last message back to the start (drops rewound branches).

    Compaction boundaries have no parentUuid; logicalParentUuid links them to the earlier part.
    """
    by_uuid = {r["uuid"]: r for r in records if isinstance(r.get("uuid"), str)}
    leaf = next((r["uuid"] for r in reversed(records)
                 if r.get("type") in ("user", "assistant") and not r.get("isSidechain")
                 and isinstance(r.get("uuid"), str)), None)
    chain: set[str] = set()
    current = leaf
    while current and current in by_uuid and current not in chain:
        chain.add(current)
        rec = by_uuid[current]
        current = rec.get("parentUuid") or rec.get("logicalParentUuid")
    return chain


def _user_entries(rec: Record) -> list[Entry]:
    ts = _parse_ts(rec.get("timestamp"))
    blocks = _blocks((rec.get("message") or {}).get("content"))
    errors = [Entry("error", _tool_error_text(b), ts) for b in blocks
              if b.get("type") == "tool_result" and b.get("is_error")]
    if errors or rec.get("toolUseResult") is not None:
        return errors
    if any(b.get("type") == "text" and str(b.get("text", "")).startswith(INTERRUPTED) for b in blocks):
        return [Entry("notice", "Interrumpido por el usuario", ts)]
    prompt = extract_prompt(rec)
    if prompt is None:
        return []
    text, is_command = prompt
    media = sum(1 for b in blocks if b.get("type") in ("image", "document"))
    if media:
        text = (text + "\n\n" if text else "") + f"[{media} adjunto{'s' if media > 1 else ''}]"
    return [Entry("command" if is_command else "user", _cut(text), ts)]


def load_transcript(path: Path) -> Transcript:
    """Read-only. Corrupt lines are skipped and reported in `warnings`."""
    result = Transcript()
    records: list[Record] = []
    bad = 0
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if isinstance(rec, dict):
                records.append(rec)
    if bad:
        result.warnings.append(f"{path.name}: {bad} línea(s) ilegibles ignoradas")

    chain = _main_chain(records)
    cwd = next((r["cwd"] for r in records if isinstance(r.get("cwd"), str)), None)
    entries = result.entries
    pending_text: dict[str, int] = {}      # message.id -> index of its merged assistant entry

    for rec in records:
        kind = rec.get("type")
        uuid = rec.get("uuid")
        if rec.get("isSidechain"):
            continue
        if kind == "system" and rec.get("subtype") == "compact_boundary":
            entries.append(Entry("notice", "Conversación compactada", _parse_ts(rec.get("timestamp"))))
            continue
        if kind not in ("user", "assistant"):
            continue
        is_tool_result = kind == "user" and rec.get("toolUseResult") is not None
        if uuid not in chain and not is_tool_result:      # abandoned branch (rewind / edit)
            continue

        if kind == "user":
            entries.extend(_user_entries(rec))
            continue

        ts = _parse_ts(rec.get("timestamp"))
        message = rec.get("message") or {}
        if rec.get("isApiErrorMessage"):
            text = " ".join(b.get("text", "") for b in _blocks(message.get("content")) if b.get("type") == "text")
            entries.append(Entry("error", one_line(text or "Error de la API", 200), ts))
            continue
        for block in _blocks(message.get("content")):
            btype = block.get("type")
            if btype == "text" and str(block.get("text", "")).strip():
                msg_id = message.get("id") or uuid
                if pending_text.get(msg_id) == len(entries) - 1:   # same API message split across records
                    i = pending_text[msg_id]
                    entries[i] = Entry("assistant", _cut(entries[i].text + "\n\n" + block["text"]), entries[i].timestamp)
                else:
                    pending_text[msg_id] = len(entries)
                    entries.append(Entry("assistant", _cut(block["text"]), ts))
            elif btype == "tool_use":
                entries.append(Entry("tool", tool_summary(str(block.get("name", "?")), block.get("input"), cwd), ts))
    return result
