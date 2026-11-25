"""Locations of Claude Code data on disk."""

import os
from pathlib import Path


def claude_home() -> Path:
    """Claude Code config dir; honours CLAUDE_CONFIG_DIR like Claude Code does."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override).expanduser() if override else Path.home() / ".claude"


def projects_dir() -> Path:
    return claude_home() / "projects"
