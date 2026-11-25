"""Single-line label that ends with '…' instead of being cut mid-word, and never widens its parent."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QStyle, QStyleOption


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        opt = QStyleOption()
        opt.initFrom(self)
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, rect.width())
        self.style().drawItemText(painter, rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                                  opt.palette, self.isEnabled(), text, self.foregroundRole())
