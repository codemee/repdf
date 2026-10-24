from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from repdf.core import (DocumentSelection, IncorrectPasswordError, PasswordRequiredError,
                        export_documents, inspect_pdf, split_documents, save_document)


class LoadSignals(QObject):
    loaded = Signal(int, object, int)
    failed = Signal(int, str)
    password_required = Signal(int, bool)


class LoadPdfTask(QRunnable):
    def __init__(self, source: Path, session_id: int, password: str | None = None) -> None:
        super().__init__()
        self.source = source
        self.session_id = session_id
        self.password = password
        self.signals = LoadSignals()

    @Slot()
    def run(self) -> None:
        try:
            info = inspect_pdf(self.source, self.password, quick=True)
            self.signals.loaded.emit(self.session_id, info.path, info.page_count)
        except (PasswordRequiredError, IncorrectPasswordError) as exc:
            self.signals.password_required.emit(self.session_id, isinstance(exc, IncorrectPasswordError))
        except Exception as exc:
            self.signals.failed.emit(self.session_id, str(exc))
        finally:
            self.password = None


class ExportSignals(QObject):
    completed = Signal(int, object, int)
    failed = Signal(int, str)


class ExportPdfTask(QRunnable):
    def __init__(
        self, documents: list[DocumentSelection], destination: Path, session_id: int,
        *, split: bool = False, overwrite: bool = False, protected_sources: tuple[Path, ...] = (),
    ) -> None:
        super().__init__()
        self.documents = tuple(DocumentSelection(item.source, tuple(item.pages), item.password, item.annotation_changes) for item in documents)
        self.destination = destination
        self.session_id = session_id
        self.signals = ExportSignals()
        self.split = split
        self.overwrite = overwrite
        self.protected_sources = protected_sources

    @Slot()
    def run(self) -> None:
        try:
            if self.split:
                count = len(split_documents(self.documents, self.destination,
                                            overwrite=self.overwrite, protected_sources=self.protected_sources))
            else:
                count = export_documents(self.documents, self.destination,
                                         protected_sources=self.protected_sources)
            self.signals.completed.emit(self.session_id, self.destination, count)
        except Exception as exc:
            self.signals.failed.emit(self.session_id, str(exc))
        finally:
            self.documents = ()


class SavePdfTask(QRunnable):
    def __init__(self, source, destination, order, password, overwrite=False, annotation_changes=()):
        super().__init__()
        self.source, self.destination, self.order = source, destination, tuple(order)
        self.annotation_changes = annotation_changes
        self.password, self.overwrite = password, overwrite
        self.signals = ExportSignals()

    @Slot()
    def run(self):
        try:
            count = save_document(self.source, self.destination, self.order,
                                  password=self.password, overwrite=self.overwrite, annotation_changes=self.annotation_changes)
            self.signals.completed.emit(0, self.destination, count)
        except Exception as exc:
            self.signals.failed.emit(0, str(exc))
        finally:
            self.password = None
