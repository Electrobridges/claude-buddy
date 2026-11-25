"""Read-only conversation viewer (QTextBrowser + Qt's built-in Markdown renderer)."""

from html import escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QPalette, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
    QTextFrameFormat, QTextOption,
)
from PySide6.QtWidgets import QFrame, QTextBrowser, QWidget

from ..timefmt import clock
from ..transcript import Entry

ACCENT = QColor("#D97757")
_MD = QTextDocument.MarkdownFeature.MarkdownDialectGitHub | QTextDocument.MarkdownFeature.MarkdownNoHTML
_ASSISTANT_RUN = ("assistant", "tool", "error")


class TranscriptView(QTextBrowser):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.document().setDocumentMargin(8)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)   # long hashes/paths
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._last: Entry | None = None        # last entry drawn (decides headers)
        self._live_start: int | None = None    # where the streaming assistant text begins
        self._empty = True

    # --- public -------------------------------------------------------------
    def show_placeholder(self, text: str) -> None:
        self.setHtml(f"<p align='center' style='color: gray; margin-top: 40px'>{escape(text)}</p>")
        self._last, self._live_start, self._empty = None, None, True

    # --- live chat (incremental) --------------------------------------------
    def append_entry(self, entry: Entry) -> None:
        """Add one entry at the end (user prompt, tool line, error, notice, full answer)."""
        with self._follow_bottom():
            self._end_live()
            cursor = self._end_cursor()
            self._append(cursor, entry, self._last, first=self._empty)
            self._last, self._empty = entry, False

    def stream_text(self, delta: str) -> None:
        """Append raw streamed text; it is re-rendered as Markdown by finish_text()."""
        with self._follow_bottom():
            cursor = self._end_cursor()
            if self._live_start is None:
                live = Entry("assistant", "")
                if self._last is None or self._last.kind not in _ASSISTANT_RUN:
                    text_color, muted, _, _ = self._colors()
                    self._header(cursor, "Claude", live, self._empty, text_color, muted)
                    self._empty = False
                self._block(cursor, self._empty, top=4)
                self._live_start, self._last, self._empty = cursor.position(), live, False
            plain = QTextCharFormat()
            plain.setForeground(self._colors()[0])
            cursor.insertText(delta, plain)

    def finish_text(self, text: str) -> None:
        """Replace the streamed text with its rendered Markdown (or append it if nothing streamed)."""
        if self._live_start is None:
            self.append_entry(Entry("assistant", text))
            return
        with self._follow_bottom():
            cursor = self._end_cursor()
            cursor.setPosition(self._live_start, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertMarkdown(text, _MD)
            self._live_start = None
            self._last = Entry("assistant", text)
            self._allow_wrapping(self._end_cursor())

    def _end_live(self) -> None:
        self._live_start = None

    def _end_cursor(self) -> QTextCursor:
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        return cursor

    def _follow_bottom(self):
        """Context manager: keep the view pinned to the bottom if it already was."""
        view = self

        class _Follow:
            def __enter__(self_inner):
                bar = view.verticalScrollBar()
                self_inner.at_bottom = bar.value() >= bar.maximum() - 8
                if view._empty:                         # drop the "loading"/placeholder text
                    view.clear()

            def __exit__(self_inner, *exc):
                if self_inner.at_bottom:
                    QTimer.singleShot(0, lambda: view.verticalScrollBar().setValue(view.verticalScrollBar().maximum()))
                return False

        return _Follow()

    def set_entries(self, entries: list[Entry], keep_scroll: bool = False) -> None:
        """Rebuild the document. keep_scroll: stay put unless the user was already at the bottom."""
        bar = self.verticalScrollBar()
        follow = not keep_scroll or bar.value() >= bar.maximum() - 8
        previous = bar.value()
        if not entries:
            self.show_placeholder("Esta sesión no tiene mensajes visibles.")
            return

        self.setUpdatesEnabled(False)
        self.clear()
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        prev: Entry | None = None
        for i, entry in enumerate(entries):
            self._append(cursor, entry, prev, first=i == 0)
            prev = entry
        self._allow_wrapping(cursor)
        cursor.endEditBlock()
        self._last, self._live_start, self._empty = prev, None, False
        self.setUpdatesEnabled(True)
        # Layout is lazy: scroll once it has been computed
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum() if follow else previous))

    def _allow_wrapping(self, cursor: QTextCursor) -> None:
        """Markdown code blocks are non-breakable; in a narrow panel that means horizontal scrolling."""
        block = self.document().begin()
        while block.isValid():
            if block.blockFormat().nonBreakableLines():
                fmt = QTextBlockFormat()
                fmt.setNonBreakableLines(False)
                cursor.setPosition(block.position())
                cursor.mergeBlockFormat(fmt)
            block = block.next()

    # --- building blocks ------------------------------------------------------
    def _colors(self) -> tuple[QColor, QColor, QColor, QColor]:
        pal = self.palette()
        text = pal.color(QPalette.ColorRole.Text)
        muted = QColor(text)
        muted.setAlphaF(0.6)
        dark = pal.color(QPalette.ColorRole.Base).lightness() < 128
        bubble = QColor(ACCENT)
        bubble.setAlphaF(0.18 if dark else 0.10)
        error = QColor("#FF8A80" if dark else "#B3261E")
        return text, muted, bubble, error

    def _block(self, cursor: QTextCursor, first: bool, top: float = 0, align=Qt.AlignmentFlag.AlignLeft) -> None:
        fmt = QTextBlockFormat()
        fmt.setTopMargin(top)
        fmt.setAlignment(align)
        if first:
            cursor.setBlockFormat(fmt)
            cursor.setBlockCharFormat(QTextCharFormat())
        else:
            cursor.insertBlock(fmt, QTextCharFormat())

    def _header(self, cursor: QTextCursor, who: str, entry: Entry, first: bool, color: QColor, muted: QColor) -> None:
        self._block(cursor, first, top=12)
        bold = QTextCharFormat()
        bold.setFontWeight(QFont.Weight.Bold)
        bold.setForeground(color)
        cursor.insertText(who, bold)
        if entry.timestamp:
            small = QTextCharFormat()
            small.setForeground(muted)
            cursor.insertText(f"  ·  {clock(entry.timestamp)}", small)

    def _append(self, cursor: QTextCursor, entry: Entry, prev: Entry | None, first: bool) -> None:
        text_color, muted, bubble, error = self._colors()
        plain = QTextCharFormat()
        plain.setForeground(text_color)

        if entry.kind in ("user", "command"):
            self._header(cursor, "Tú", entry, first, ACCENT, muted)
            frame = QTextFrameFormat()
            frame.setBackground(bubble)
            frame.setPadding(8)
            frame.setTopMargin(4)
            frame.setBorder(0)
            cursor.insertFrame(frame)
            fmt = QTextCharFormat(plain)
            if entry.kind == "command":
                fmt.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            cursor.insertText(entry.text, fmt)
            cursor.movePosition(QTextCursor.MoveOperation.End)       # leave the frame
            return

        if entry.kind in _ASSISTANT_RUN and (prev is None or prev.kind not in _ASSISTANT_RUN):
            self._header(cursor, "Claude", entry, first, text_color, muted)
            first = False

        if entry.kind == "assistant":
            self._block(cursor, first, top=4)
            cursor.insertMarkdown(entry.text, _MD)
            cursor.movePosition(QTextCursor.MoveOperation.End)       # never stay inside a table/list
        elif entry.kind == "tool":
            self._block(cursor, first, top=2)
            fmt = QTextCharFormat()
            fmt.setForeground(muted)
            fmt.setFontPointSize(max(7.0, self.font().pointSizeF() * 0.9))
            cursor.insertText(f"▸  {entry.text}", fmt)
        elif entry.kind == "error":
            self._block(cursor, first, top=2)
            fmt = QTextCharFormat()
            fmt.setForeground(error)
            cursor.insertText(f"⚠  {entry.text}", fmt)
        elif entry.kind == "notice":
            self._block(cursor, first, top=12, align=Qt.AlignmentFlag.AlignHCenter)
            fmt = QTextCharFormat()
            fmt.setForeground(muted)
            fmt.setFontItalic(True)
            cursor.insertText(f"— {entry.text} —", fmt)
