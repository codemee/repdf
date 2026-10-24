"""Per-document annotation baseline, deltas and undo history."""

from copy import deepcopy
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack


class Change(QUndoCommand):
    def __init__(self, store, updates, label):
        super().__init__(label)
        self.store = store
        self.after = deepcopy(updates)
        self.before = {key: deepcopy(store.items.get(key)) for key in updates}

    def redo(self):
        self.store.apply(self.after)

    def undo(self):
        self.store.apply(self.before)


class AnnotationStore(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = {}
        self.order = []
        self.baseline = {}
        self.loaded = set()
        self.geometries = {}
        self.reasons = {}
        self.undo = QUndoStack(self)
        self.revision = 0

    def load(self, page, models, geometry, reasons=None):
        self.geometries[page] = geometry
        self.reasons[page] = reasons or {}
        if page in self.loaded:
            return
        self.loaded.add(page)
        for model in models:
            if model["id"] not in self.order:
                self.order.append(model["id"])
            self.items[model["id"]] = deepcopy(model)
            self.baseline[model["id"]] = deepcopy(model)

    def apply(self, updates):
        for key, value in updates.items():
            if value is None:
                self.items.pop(key, None)
            else:
                if key not in self.order:
                    self.order.append(key)
                self.items[key] = deepcopy(value)
        self.revision += 1
        self.changed.emit()

    def change(self, updates, label):
        self.undo.push(Change(self, updates, label))

    def page(self, index):
        return [
            self.items[key]
            for key in self.order
            if key in self.items and self.items[key]["page"] == index
        ]

    def changes(self):
        result = []
        for key in self.order:
            current, original = self.items.get(key), self.baseline.get(key)
            if current == original:
                continue
            if current is None:
                result.append(
                    {
                        "id": key,
                        "page": original["page"],
                        "source_index": original["source_index"],
                        "deleted": True,
                    }
                )
            else:
                result.append(deepcopy(current))
        return result

    @property
    def modified(self):
        return bool(self.changes())
