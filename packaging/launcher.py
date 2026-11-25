"""PyInstaller entry point for the packaged Claude Buddy app."""

import sys

from claude_buddy.app import main

if __name__ == "__main__":
    sys.exit(main())
