from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from javsorter.core.models import MatchStatus, ScanItem

_COLUMNS = ["Filename", "Parsed ID", "Status", "Matched Title", "Notes"]

_STATUS_LABELS = {
    MatchStatus.NO_ID: "No ID found",
    MatchStatus.AMBIGUOUS_ID: "Ambiguous (-C marker)",
    MatchStatus.ID_FOUND: "Looking up...",
    MatchStatus.MATCHED: "Matched",
    MatchStatus.MULTIPLE_CANDIDATES: "Multiple candidates",
    MatchStatus.NO_MATCH: "No match on r18.dev",
    MatchStatus.ERROR: "Error",
}


class ScanTableModel(QAbstractTableModel):
    def __init__(self, items: list[ScanItem] | None = None):
        super().__init__()
        self._items: list[ScanItem] = items or []

    def set_items(self, items: list[ScanItem]) -> None:
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def item_at(self, row: int) -> ScanItem:
        return self._items[row]

    def update_row(self, row: int) -> None:
        top_left = self.index(row, 0)
        bottom_right = self.index(row, len(_COLUMNS) - 1)
        self.dataChanged.emit(top_left, bottom_right)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        item = self._items[index.row()]
        column = index.column()
        if column == 0:
            return ", ".join(p.name for p in item.parts)
        if column == 1:
            return item.extracted.content_id or "-"
        if column == 2:
            return _STATUS_LABELS.get(item.status, item.status.name)
        if column == 3:
            return item.metadata.title if item.metadata else ""
        if column == 4:
            return item.note or ""
        return None
