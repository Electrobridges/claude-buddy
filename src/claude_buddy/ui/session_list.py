"""Tree model of sessions grouped by project, search filter and a two-line item delegate."""

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QRectF, QSize, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTreeView

from ..models import ProjectGroup, SessionInfo
from ..search import fold, matches
from ..timefmt import relative
from .icons import ACCENT

SESSION_ROLE = Qt.ItemDataRole.UserRole + 1
SEARCH_ROLE = Qt.ItemDataRole.UserRole + 2
GROUP_KEY_ROLE = Qt.ItemDataRole.UserRole + 3

_ORIGINS = {"claude-vscode": "VS Code", "claude-desktop": "Desktop", "cli": "CLI"}


def origin_label(entrypoint: str | None) -> str:
    return _ORIGINS.get(entrypoint or "", entrypoint or "origen desconocido")


def build_model(model: QStandardItemModel, groups: list[ProjectGroup]) -> None:
    model.clear()
    root = model.invisibleRootItem()
    for group in groups:
        g_item = QStandardItem(f"{group.name}  ·  {len(group.sessions)}")
        g_item.setData(group.key, GROUP_KEY_ROLE)
        g_item.setData(fold(f"{group.name} {group.cwd or ''}"), SEARCH_ROLE)
        g_item.setToolTip(group.cwd or group.key)
        g_item.setEditable(False)
        g_item.setSelectable(False)
        font = g_item.font()
        font.setBold(True)
        g_item.setFont(font)
        for s in group.sessions:
            s_item = QStandardItem(s.title)
            s_item.setData(s, SESSION_ROLE)
            s_item.setData(fold(f"{s.title} {s.session_id} {group.name} {s.cwd or ''}"), SEARCH_ROLE)
            s_item.setToolTip(f"{s.title}\n\n{s.cwd or group.name}\nID: {s.session_id}")
            s_item.setEditable(False)
            g_item.appendRow(s_item)
        root.appendRow(g_item)


class SessionFilter(QSortFilterProxyModel):
    """Accent-insensitive, multi-word filter. A matching project shows all its sessions."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._query = ""
        self.setRecursiveFilteringEnabled(True)
        self.setAutoAcceptChildRows(True)

    @property
    def query(self) -> str:
        return self._query

    def set_query(self, query: str) -> None:
        query = query.strip()
        if query == self._query:
            return
        if hasattr(self, "beginFilterChange"):          # Qt >= 6.9
            self.beginFilterChange()
            self._query = query
            self.endFilterChange()
        else:
            self._query = query
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex) -> bool:
        if not self._query:
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        return matches(self._query, index.data(SEARCH_ROLE) or "")


class SessionTree(QTreeView):
    """Session rows have no expander: skip the branch area so the style can't tint it on selection."""

    def drawBranches(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> None:
        if index.data(SESSION_ROLE) is None:
            super().drawBranches(painter, rect, index)


def _small_font(base: QFont) -> QFont:
    small = QFont(base)
    if base.pointSizeF() > 0:
        small.setPointSizeF(max(7.0, base.pointSizeF() * 0.88))
    elif base.pixelSize() > 0:
        small.setPixelSize(max(9, round(base.pixelSize() * 0.88)))
    return small


class SessionDelegate(QStyledItemDelegate):
    """Session rows: title on top, '<when> · <n> mensajes · <origin>' underneath."""

    PAD = 6

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        fm = QFontMetrics(option.font)
        if index.data(SESSION_ROLE) is None:
            return QSize(0, fm.height() + 12)
        small = QFontMetrics(_small_font(option.font))
        return QSize(0, fm.height() + small.height() + 3 + 2 * self.PAD)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        session: SessionInfo | None = index.data(SESSION_ROLE)
        if session is None:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        view = self.parent()
        # The view uses NoSelection (the style would tint the indent); the current row is "selected"
        selected = bool(opt.state & QStyle.StateFlag.State_Selected) or (
            isinstance(view, QTreeView) and view.currentIndex() == index)
        hovered = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        # Own selection look: readable on every style/theme (no white-on-light text)
        color = opt.palette.color(QPalette.ColorRole.Text)
        muted = QColor(color)
        muted.setAlphaF(0.62)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        card = QRectF(opt.rect).adjusted(1, 1, -2, -1)
        if selected:
            tint = QColor(ACCENT)
            tint.setAlphaF(0.16)
            painter.setBrush(tint)
            painter.drawRoundedRect(card, 6, 6)
            painter.setBrush(ACCENT)
            painter.drawRoundedRect(QRectF(card.left(), card.top() + 5, 3, card.height() - 10), 1.5, 1.5)
        elif hovered:
            tint = QColor(color)
            tint.setAlphaF(0.06)
            painter.setBrush(tint)
            painter.drawRoundedRect(card, 6, 6)
        painter.restore()

        rect = opt.rect.adjusted(self.PAD + 4, self.PAD, -self.PAD, -self.PAD)
        fm = QFontMetrics(opt.font)
        small = _small_font(opt.font)
        sfm = QFontMetrics(small)
        meta = f"{relative(session.last_activity)}  ·  {session.message_count} mensajes  ·  {origin_label(session.entrypoint)}"

        painter.save()
        painter.setFont(opt.font)
        painter.setPen(color)
        painter.drawText(QRect(rect.left(), rect.top(), rect.width(), fm.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         fm.elidedText(session.title, Qt.TextElideMode.ElideRight, rect.width()))
        painter.setFont(small)
        painter.setPen(muted)
        painter.drawText(QRect(rect.left(), rect.top() + fm.height() + 3, rect.width(), sfm.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         sfm.elidedText(meta, Qt.TextElideMode.ElideRight, rect.width()))
        painter.restore()
