"""Reusable widgets: a sortable read-only table and dashboard stat cards."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QTableView, QVBoxLayout, QWidget,
)

from inventory_app.csv_io import write_csv
from inventory_app.ui import theme


@dataclass
class Column:
    header: str
    key: str
    fmt: Callable[[Any], str] | None = None
    numeric: bool = False

    def display(self, value: Any) -> str:
        if value is None:
            return ""
        return self.fmt(value) if self.fmt else str(value)


class RowTableModel(QAbstractTableModel):
    def __init__(self, columns: list[Column], highlight: Callable[[dict], bool] | None, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.highlight = highlight
        self.rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = [dict(r) for r in rows]
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
        row = self.rows[index.row()]
        column = self.columns[index.column()]
        value = row.get(column.key)
        if role == Qt.ItemDataRole.DisplayRole:
            return column.display(value)
        if role == Qt.ItemDataRole.UserRole:  # sort key
            if value is None:
                return 0 if column.numeric else ""
            return value if column.numeric else str(value).lower()
        if role == Qt.ItemDataRole.TextAlignmentRole:
            horizontal = Qt.AlignmentFlag.AlignRight if column.numeric else Qt.AlignmentFlag.AlignLeft
            return int(horizontal | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and self.highlight and self.highlight(row):
            return QBrush(theme.color("danger"))
        return None


class DataTable(QTableView):
    """Read-only, sortable table fed with a list of dicts."""

    def __init__(self, columns: list[Column], highlight: Callable[[dict], bool] | None = None, parent=None):
        super().__init__(parent)
        self.source = RowTableModel(columns, highlight, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.source)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.setModel(self.proxy)
        # Keep the order the rows arrive in until the user clicks a header.
        self.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setHighlightSections(False)

    def set_rows(self, rows: list[dict]) -> None:
        selected = self.selected()
        self.source.set_rows(rows)
        self.resizeColumnsToContents()
        for col in range(self.source.columnCount()):
            if self.columnWidth(col) > 320:
                self.setColumnWidth(col, 320)
        if selected and "id" in selected:
            self.select_id(selected["id"])

    def select_id(self, row_id: Any) -> None:
        for i, row in enumerate(self.source.rows):
            if row.get("id") == row_id:
                index = self.proxy.mapFromSource(self.source.index(i, 0))
                self.selectRow(index.row())
                return

    def selected(self) -> dict | None:
        rows = self.selectionModel().selectedRows() if self.selectionModel() else []
        if not rows:
            return None
        return self.source.rows[self.proxy.mapToSource(rows[0]).row()]

    def visible_table(self) -> tuple[list[str], list[list[str]]]:
        """Headers and displayed text of every row, in the current sort order."""
        columns = self.source.columns
        data = []
        for r in range(self.proxy.rowCount()):
            source_row = self.source.rows[self.proxy.mapToSource(self.proxy.index(r, 0)).row()]
            data.append([c.display(source_row.get(c.key)) for c in columns])
        return [c.header for c in columns], data

    def export_csv(self, parent: QWidget, default_name: str) -> None:
        path, _ = QFileDialog.getSaveFileName(parent, "Export to CSV", default_name, "CSV files (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        headers, rows = self.visible_table()
        try:
            write_csv(path, headers, rows)
        except OSError as exc:
            QMessageBox.critical(parent, "Export failed", str(exc))
            return
        QMessageBox.information(parent, "Export complete", f"Exported {len(rows)} rows to\n{path}")


class Tile(QFrame):
    """Overview stat: icon badge, big number and caption."""

    def __init__(self, icon_name: str, caption: str, tone: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Tile")
        self.setProperty("tone", tone)
        self.icon_name, self.tone = icon_name, tone
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 18, 12)
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

    def set_value(self, text: str) -> None:
        self.value.setText(text)


class Card(QFrame):
    """Rounded panel with a title row; add content to .body."""

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


def heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionHeading")
    return label


def confirm(parent: QWidget, title: str, text: str) -> bool:
    answer = QMessageBox.question(parent, title, text,
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
    return answer == QMessageBox.StandardButton.Yes
