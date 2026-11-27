"""Reusable widgets: sortable table, checklist dropdown, stat tiles, cards, sidebar items, message helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSize, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QFont, QPainter, QPen, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QStyle, QStyleOptionComboBox, QStylePainter, QTableView, QVBoxLayout, QWidget,
)

from saims.desktop.api import ApiError
from saims.desktop.ui import formatting as fmt
from saims.desktop.ui import theme


@dataclass
class Column:
    header: str
    key: str
    fmt: Callable[[Any], str] | None = None
    numeric: bool = False
    color: Callable[[dict], str | None] | None = None  # row → theme token for the text colour
    width: int | None = None

    def display(self, row: dict) -> str:
        value = row.get(self.key)
        if value is None or value == "":
            return ""
        return self.fmt(value) if self.fmt else str(value)


def money_col(header: str, key: str) -> Column:
    return Column(header, key, fmt.money, numeric=True)


def qty_col(header: str, key: str) -> Column:
    return Column(header, key, fmt.qty, numeric=True)


class RowTableModel(QAbstractTableModel):
    def __init__(self, columns: list[Column], row_color: Callable[[dict], str | None] | None, parent=None):
        super().__init__(parent)
        self.columns, self.row_color = columns, row_color
        self.rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.columns[section].header
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = self.rows[index.row()], self.columns[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return col.display(row)
        if role == Qt.ItemDataRole.UserRole:
            value = row.get(col.key)
            if col.numeric:
                return float(fmt.dec(value))
            return "" if value is None else str(value).lower()
        if role == Qt.ItemDataRole.TextAlignmentRole:
            h = Qt.AlignmentFlag.AlignRight if col.numeric else Qt.AlignmentFlag.AlignLeft
            return int(h | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            token = (col.color(row) if col.color else None) or (self.row_color(row) if self.row_color else None)
            return QBrush(theme.color(token)) if token else None
        if role == Qt.ItemDataRole.ToolTipRole:
            text = col.display(row)
            return text if len(text) > 30 else None
        return None


class DataTable(QTableView):
    """Read-only, sortable table fed with a list of dicts (rows keep an "id")."""

    def __init__(self, columns: list[Column], row_color=None, parent=None, multi: bool = False):
        super().__init__(parent)
        self.source = RowTableModel(columns, row_color, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.source)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.setModel(self.proxy)
        self.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection if multi
                              else QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(30)
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setHighlightSections(False)

    def set_rows(self, rows: list[dict]) -> None:
        keep = [r.get("id") for r in self.selected_rows()]
        self.source.set_rows(rows)
        self.resizeColumnsToContents()
        for i, col in enumerate(self.source.columns):
            if col.width:
                self.setColumnWidth(i, col.width)
            elif self.columnWidth(i) > 300:
                self.setColumnWidth(i, 300)
        if keep:
            self.select_ids(keep)

    def select_id(self, row_id: Any) -> None:
        self.select_ids([row_id])

    def select_ids(self, row_ids: list[Any]) -> None:
        """Select the rows with these ids (keeps a multi-row selection across refreshes)."""
        wanted = set(row_ids)
        sm = self.selectionModel()
        sm.clearSelection()
        first = None
        for i, row in enumerate(self.source.rows):
            if row.get("id") in wanted:
                index = self.proxy.mapFromSource(self.source.index(i, 0))
                sm.select(index, sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
                first = first or index
        if first is not None:
            sm.setCurrentIndex(first, sm.SelectionFlag.NoUpdate)
            self.scrollTo(first)

    def selected_rows(self) -> list[dict]:
        """Selected rows in the order shown."""
        sm = self.selectionModel()
        indexes = sorted(sm.selectedRows(), key=lambda i: i.row()) if sm else []
        return [self.source.rows[self.proxy.mapToSource(i).row()] for i in indexes]

    def selected(self) -> dict | None:
        """The selected row when exactly one is selected (single-record actions), else None."""
        rows = self.selected_rows()
        return rows[0] if len(rows) == 1 else None

    def visible_table(self, selected_only: bool = False) -> tuple[list[str], list[list[str]]]:
        cols = self.source.columns
        if selected_only:
            rows = self.selected_rows()
        else:
            rows = [self.source.rows[self.proxy.mapToSource(self.proxy.index(r, 0)).row()]
                    for r in range(self.proxy.rowCount())]
        return [c.header for c in cols], [[c.display(row) for c in cols] for row in rows]


class CheckCombo(QComboBox):
    """Dropdown checklist for filters: tick any number of options. Nothing ticked means "all".

    The popup stays open while ticking; `changed` fires once when it closes (and on programmatic changes)."""

    changed = Signal()

    def __init__(self, all_label: str, noun: str = "", clear_label: str | None = None, parent=None):
        """`all_label` is shown when nothing is ticked; the first row (`clear_label`) unticks everything."""
        super().__init__(parent)
        self.all_label, self.noun = all_label, noun or all_label.replace("All ", "")
        self.clear_label = clear_label or f"{all_label} (clear ticks)"
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self._keep_open = False
        self._opened_with: list = []
        self.view().pressed.connect(self._toggle_index)
        self.setMinimumContentsLength(12)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.set_options([])

    # ------------------------------------------------------------ options
    def set_options(self, options: list[tuple[str, Any]]) -> None:
        """Replace the options, keeping ticks on values that still exist."""
        keep = set(self.values())
        self._model.clear()
        clear = QStandardItem(self.clear_label)
        clear.setData("__all__", Qt.ItemDataRole.UserRole)
        self._model.appendRow(clear)
        for label, value in options:
            item = QStandardItem(label)
            item.setData(value, Qt.ItemDataRole.UserRole)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.CheckState.Checked if value in keep else Qt.CheckState.Unchecked,
                         Qt.ItemDataRole.CheckStateRole)
            self._model.appendRow(item)
        self.setCurrentIndex(0)
        self.update()

    def values(self) -> list:
        out = []
        for row in range(1, self._model.rowCount()):
            item = self._model.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out

    def set_values(self, values: list, emit: bool = True) -> None:
        wanted = set(values)
        for row in range(1, self._model.rowCount()):
            item = self._model.item(row)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in wanted
                               else Qt.CheckState.Unchecked)
        self.update()
        if emit:
            self.changed.emit()

    def clear_selection(self, emit: bool = True) -> None:
        self.set_values([], emit)

    def summary(self) -> str:
        labels = [self._model.item(r).text() for r in range(1, self._model.rowCount())
                  if self._model.item(r).checkState() == Qt.CheckState.Checked]
        if not labels:
            return self.all_label
        text = ", ".join(labels)
        if len(labels) == 1 or self.fontMetrics().horizontalAdvance(text) < self.width() - 40:
            return text
        return f"{len(labels)} {self.noun.lower()}"

    # ------------------------------------------------------------ behaviour
    def _toggle_index(self, index) -> None:
        item = self._model.itemFromIndex(index)
        if item is None:
            return
        if item.data(Qt.ItemDataRole.UserRole) == "__all__":
            self.set_values([], emit=False)
            self._keep_open = False  # "show all" closes the list
            return
        item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked
                           else Qt.CheckState.Checked)
        self._keep_open = True
        self.update()

    def keyPressEvent(self, event) -> None:
        if self.view().isVisible() and event.key() == Qt.Key.Key_Space:
            self._toggle_index(self.view().currentIndex())
            return
        super().keyPressEvent(event)

    def showPopup(self) -> None:
        self._opened_with = self.values()
        super().showPopup()

    def hidePopup(self) -> None:
        if self._keep_open:  # the click that ticked an option: keep the list open
            self._keep_open = False
            return
        super().hidePopup()
        self.setCurrentIndex(0)
        if self.values() != self._opened_with:
            self.changed.emit()

    def paintEvent(self, _event) -> None:
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = self.summary()
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, opt)


class Tile(QFrame):
    """Overview stat: icon badge, big number, caption and an optional sub-line."""

    def __init__(self, icon_name: str, caption: str, tone: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Tile")
        self.setProperty("tone", tone)
        self.icon_name, self.tone = icon_name, tone
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 16, 12)
        layout.setSpacing(12)
        self.icon = QLabel()
        self.icon.setObjectName("TileIcon")
        self.icon.setProperty("tone", tone)
        self.icon.setFixedSize(40, 40)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.value = QLabel("–")
        self.value.setObjectName("TileValue")
        self.caption = QLabel(caption)
        self.caption.setObjectName("TileCaption")
        text.addWidget(self.value)
        text.addWidget(self.caption)
        layout.addWidget(self.icon)
        layout.addLayout(text, 1)
        self.update_icon()

    def update_icon(self) -> None:
        token = "warn_fg" if self.tone == "warn" else "icon_fg"
        self.icon.setPixmap(theme.pixmap(self.icon_name, theme.color(token).name(), 22))

    def set_value(self, text: str, caption: str | None = None) -> None:
        self.value.setText(text)
        if caption is not None:
            self.caption.setText(caption)


class NavItem(QAbstractButton):
    """Sidebar entry, painted directly: a rounded pill inset in the sidebar, a vector icon and the label.

    Painting it ourselves (instead of styling a QPushButton) keeps the icon, text and pill aligned and sharp at any
    display scale, and gives the same result whatever Qt style or platform theme is in use."""

    HEIGHT, RADIUS, PAD, ICON, GAP = 40, 10, 14, 20, 12

    def __init__(self, text: str, icon_name: str, checkable: bool = True, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setAccessibleName(text)
        self.icon_name = icon_name
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(self.HEIGHT)
        self._keyboard_focus = False

    def focusInEvent(self, event) -> None:
        # Only show the focus ring when focus arrived from the keyboard, not on start-up or a click.
        self._keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._keyboard_focus = False
        super().focusOutEvent(event)

    def sizeHint(self) -> QSize:
        width = self.PAD * 2 + self.ICON + self.GAP + self.fontMetrics().horizontalAdvance(self.text())
        return QSize(width, self.HEIGHT)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        active = self.isChecked()
        if active or self.isDown() or self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("nav_active_bg" if active else "sidebar_hover"))
            p.drawRoundedRect(rect, self.RADIUS, self.RADIUS)
        if self.hasFocus() and self._keyboard_focus:
            p.setPen(QPen(theme.color("sidebar_muted"), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), self.RADIUS - 1, self.RADIUS - 1)
        fg = theme.color("nav_active_text" if active else "sidebar_text")
        top = (self.height() - self.ICON) / 2
        theme.paint_icon(p, self.icon_name, fg.name(), QRectF(self.PAD, top, self.ICON, self.ICON))
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold if active else QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(fg)
        left = self.PAD + self.ICON + self.GAP
        p.drawText(QRectF(left, 0, self.width() - left - 8, self.height()),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self.text())
        p.end()


class Card(QFrame):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(8)
        self.title_row = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        self.title_row.addWidget(self.title)
        self.title_row.addStretch()
        self.subtitle = QLabel()
        self.subtitle.setObjectName("CardSub")
        self.title_row.addWidget(self.subtitle)
        if title:
            outer.addLayout(self.title_row)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body, 1)


def confirm(parent: QWidget, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes


def show_error(parent: QWidget, exc: Exception, title: str = "Could not complete the action") -> None:
    QMessageBox.warning(parent, title, exc.message if isinstance(exc, ApiError) else str(exc))


def hint(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    return label


STATUS_TOKENS = {
    "available": "ok", "assigned": "info", "borrowed": "info", "under_maintenance": "warning",
    "damaged": "danger", "missing": "danger", "retired": "muted", "disposed": "muted",
    "pending": "warning", "approved": "info", "released": "info", "returned": "ok", "rejected": "muted",
    "cancelled": "muted", "lost": "danger", "low": "warning", "out": "danger", "ok": "ok",
}


def status_color(key: str = "status") -> Callable[[dict], str | None]:
    return lambda row: STATUS_TOKENS.get(row.get(key, ""))
