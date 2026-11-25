"""Crisp line icons drawn with QPainter on a 24x24 grid (no image files; colour follows the palette)."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

ACCENT = QColor("#D97757")
_SIZES = (16, 18, 20, 24, 28, 32, 40, 48, 64)
NAMES = ("refresh", "pin", "more", "close", "back", "send", "stop", "terminal")


def _arrow_head(p: QPainter, tip: QPointF, direction: QPointF, size: float) -> None:
    d = math.hypot(direction.x(), direction.y()) or 1.0
    ux, uy = direction.x() / d, direction.y() / d
    base = QPointF(tip.x() - ux * size, tip.y() - uy * size)
    nx, ny = -uy * size * 0.75, ux * size * 0.75
    p.drawPolygon(QPolygonF([tip, QPointF(base.x() + nx, base.y() + ny), QPointF(base.x() - nx, base.y() - ny)]))


def _draw(p: QPainter, name: str, color: QColor, checked: bool) -> None:
    pen = QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    if name == "refresh":                       # open circle with a clockwise arrow head
        p.drawArc(QRectF(5, 5, 14, 14), 40 * 16, 290 * 16)
        theta = math.radians(40)
        tip = QPointF(12 + 7 * math.cos(theta), 12 - 7 * math.sin(theta))
        p.setBrush(QBrush(color))
        p.setPen(QPen(color, 1.0))
        _arrow_head(p, QPointF(tip.x() + 1.2, tip.y() + 2.2), QPointF(math.sin(theta), math.cos(theta)), 4.2)
    elif name == "pin":                         # thumbtack, filled with the accent when checked
        body = QPainterPath()
        body.moveTo(9, 4)
        body.lineTo(15, 4)
        body.lineTo(14.5, 10)
        body.lineTo(18, 14)
        body.lineTo(6, 14)
        body.lineTo(9.5, 10)
        body.closeSubpath()
        if checked:
            p.setBrush(QBrush(ACCENT))
            p.setPen(QPen(ACCENT, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(body)
        p.drawLine(QPointF(12, 14), QPointF(12, 20.5))
    elif name == "more":                        # three bold dots
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        for x in (5.5, 12, 18.5):
            p.drawEllipse(QPointF(x, 12), 2.1, 2.1)
    elif name == "close":
        p.drawLine(QPointF(7, 7), QPointF(17, 17))
        p.drawLine(QPointF(17, 7), QPointF(7, 17))
    elif name == "back":
        p.drawLine(QPointF(19, 12), QPointF(5.5, 12))
        p.drawPolyline(QPolygonF([QPointF(11, 6.5), QPointF(5.5, 12), QPointF(11, 17.5)]))
    elif name == "send":                        # paper plane, filled
        plane = QPainterPath()
        plane.moveTo(3.5, 11)
        plane.lineTo(20.5, 3.5)
        plane.lineTo(13, 20.5)
        plane.lineTo(11, 13)
        plane.closeSubpath()
        p.setBrush(QBrush(color))
        p.drawPath(plane)
    elif name == "terminal":                    # window with a >_ prompt
        p.drawRoundedRect(QRectF(3.5, 5, 17, 14), 2.5, 2.5)
        p.drawPolyline(QPolygonF([QPointF(7.5, 9.5), QPointF(10.5, 12), QPointF(7.5, 14.5)]))
        p.drawLine(QPointF(12.5, 15), QPointF(16.5, 15))
    elif name == "stop":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        p.drawRoundedRect(QRectF(6.5, 6.5, 11, 11), 2.5, 2.5)


def _render(name: str, px: int, color: QColor, checked: bool) -> QPixmap:
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(px / 24, px / 24)
    _draw(p, name, color, checked)
    p.end()
    return pixmap


def make_icon(name: str, color: QColor, checkable: bool = False) -> QIcon:
    """Icon with pixmaps for every common size (Qt picks/scales per DPI). Checkable icons get an On state."""
    icon = QIcon()
    for px in _SIZES:
        icon.addPixmap(_render(name, px, color, False), QIcon.Mode.Normal, QIcon.State.Off)
        if checkable:
            icon.addPixmap(_render(name, px, color, True), QIcon.Mode.Normal, QIcon.State.On)
    return icon
