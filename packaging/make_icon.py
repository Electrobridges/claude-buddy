"""Generate build/claude-buddy.ico (multi-size, PNG entries) from the pixel buddy sprite."""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from claude_buddy.ui import sprites  # noqa: E402
from claude_buddy.ui.mascot import render  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(size: int) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    render(sprites.frame("idle", 0), "terracotta", size).save(buffer, "PNG")
    return bytes(data.data())


def main(out: Path) -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for QPixmap
    images = [png_bytes(s) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in zip(SIZES, images, strict=True):
        dim = 0 if size >= 256 else size                 # 0 means 256 in ICO headers
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        blobs += blob
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(header + entries + blobs)
    print(f"icon written: {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/claude-buddy.ico"))
