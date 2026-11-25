"""Data models."""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SessionInfo:
    session_id: str
    file: Path
    project_folder: str          # encoded folder name under ~/.claude/projects
    cwd: str | None              # original working directory (first cwd in the file)
    title: str
    last_activity: datetime      # timezone-aware (UTC)
    message_count: int
    entrypoint: str | None       # cli, claude-vscode, claude-desktop, sdk-*

    @property
    def project_name(self) -> str:
        """Short display name: last path component of cwd."""
        if not self.cwd:
            return self.project_folder
        parts = [p for p in re.split(r"[\\/]", self.cwd) if p]
        return parts[-1] if parts else self.cwd

    @property
    def project_key(self) -> str:
        """Grouping key; case-insensitive on Windows (CLI and VS Code differ in drive case)."""
        return os.path.normcase(self.cwd) if self.cwd else self.project_folder


@dataclass(frozen=True, slots=True)
class ProjectGroup:
    key: str
    name: str
    cwd: str | None
    sessions: tuple[SessionInfo, ...]   # newest first


def group_by_project(sessions: list[SessionInfo]) -> list[ProjectGroup]:
    """Group sessions by project; groups ordered by their most recent session."""
    buckets: dict[str, list[SessionInfo]] = {}
    for s in sorted(sessions, key=lambda s: s.last_activity, reverse=True):
        buckets.setdefault(s.project_key, []).append(s)
    return [ProjectGroup(key, items[0].project_name, items[0].cwd, tuple(items))
            for key, items in buckets.items()]
