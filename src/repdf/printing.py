"""Print immutable page selections through a separate, bounded PDFium backend."""

from dataclasses import dataclass, field
from pathlib import Path
import re
import tempfile

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPageLayout, QPainter
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout,
                              QLabel, QLineEdit, QMessageBox, QProgressDialog, QVBoxLayout, QWidget)

from repdf.renderer import RenderService, start_render_backend
from repdf.strings import tr


@dataclass(frozen=True)
class PrintPage:
    source: Path
    page: int
    password: str | None = field(default=None, repr=False)
    annotation_changes: tuple = field(default=(), repr=False)


def parse_page_range(text, count):
    pages = set()
    for part in text.split(','):
        match = re.fullmatch(r'\s*([0-9]+)\s*(?:-\s*([0-9]+)\s*)?', part)
        if not match:
            raise ValueError(tr('請輸入有效頁次，例如 1,3,5-8。'))
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= count:
            raise ValueError(tr('頁次必須介於 1–{p0}，範圍起點不可大於終點。', p0=count))
        pages.update(range(first - 1, last))
    return pages


def selected_print_pages(documents):
    return tuple(PrintPage(item.source, page, item.password, item.annotation_changes)
                 for item in documents for page in item.pages)


class PrintOptions(QWidget):
    selection_changed = Signal()

    def __init__(self, owner, doc, current_page):
        super().__init__(owner)
        self.setMinimumWidth(0)
        annotation_snapshot = tuple(doc.annotation_store.changes())
        self.all_pages = tuple(PrintPage(doc.source_path, page, doc.password, annotation_snapshot) for page in doc.page_order)
        self.current_page = current_page
        self.selected_pages = selected_print_pages(owner.output_selection())
        self.pages = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = self.form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.scope = QComboBox()
        for text, value in (('目前文件全部頁面', 'all'), ('目前頁面', 'current'),
                            ('指定頁次', 'range'), ('勾選頁面', 'selected')):
            self.scope.addItem(tr(text), value)
        form.addRow(tr('列印範圍'), self.scope)
        self.scope_hint = QLabel()
        self.scope_hint.setWordWrap(True)
        self.scope_hint.setTextFormat(Qt.TextFormat.PlainText)
        form.addRow(self.scope_hint)
        self.checked_tabs = any(d.include_checkbox.isChecked() for d in owner.ordered_documents())
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText('1,3,5-8')
        self.range_edit.setMaxLength(4096)
        self.range_edit.setAccessibleName(tr('原始 PDF 頁次'))
        form.addRow(tr('原始 PDF 頁次'), self.range_edit)
        self.scaling = QComboBox()
        self.scaling.addItem(tr('符合可列印範圍'), 'fit')
        self.scaling.addItem(tr('實際大小'), 'actual')
        form.addRow(tr('縮放'), self.scaling)
        self.scaling_hint = QLabel()
        self.scaling_hint.setWordWrap(True)
        form.addRow(self.scaling_hint)
        layout.addLayout(form)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.scope.currentIndexChanged.connect(self.update_selection)
        self.range_edit.textChanged.connect(self.update_selection)
        self.scaling.currentIndexChanged.connect(self.update_scaling_hint)
        self.update_selection()
        self.update_scaling_hint()

    def update_scaling_hint(self):
        self.scaling_hint.setText(tr('依紙張可列印範圍等比例放大或縮小，完整放入並置中。')
            if self.scaling.currentData() == 'fit' else
            tr('維持 PDF 原始尺寸並置中；超出可列印範圍的內容會被裁切。'))

    def update_selection(self):
        scope = self.scope.currentData()
        self.range_edit.setEnabled(scope == 'range')
        self.form.setRowVisible(self.range_edit, scope == 'range')
        hints = {
            'all': tr('列印目前文件的全部頁面，依畫面排列順序。'),
            'current': tr('只列印目前正在閱讀的原始第 {p0} 頁。', p0=self.current_page + 1),
            'range': tr('輸入原始 PDF 頁碼，例如 1,3,5-8；依畫面排列順序列印。'),
            'selected': tr('列印已勾選標籤內的勾選頁面，依標籤與頁面排列順序。') if self.checked_tabs else
                        tr('未勾選標籤，僅列印目前標籤內的勾選頁面。'),
        }
        self.scope_hint.setText(hints[scope])
        try:
            if scope == 'selected':
                pages = self.selected_pages
            elif scope == 'current':
                pages = tuple(p for p in self.all_pages if p.page == self.current_page)
            elif scope == 'range':
                selected = parse_page_range(self.range_edit.text(), len(self.all_pages))
                pages = tuple(p for p in self.all_pages if p.page in selected)
            else:
                pages = self.all_pages
            if not pages:
                raise ValueError(tr('沒有勾選頁面，請先勾選要列印的頁面。') if scope == 'selected' else tr('請至少選取一頁。'))
            self.pages = pages
            self.summary.setText(tr('列印 {p0} 份文件，共 {p1} 頁',
                                    p0=len({p.source for p in pages}), p1=len(pages)))
        except ValueError as exc:
            self.pages = ()
            self.summary.setText('' if scope == 'range' and not self.range_edit.text().strip() else str(exc))
        self.selection_changed.emit()


def ordered_print_pages(printer, pages):
    """Resolve ranges and order without changing the printer configuration."""
    pages = tuple(pages)
    if printer.printRange() == QPrinter.PrintRange.PageRange:
        ranges = printer.pageRanges().toRangeList()
        if ranges:
            pages = tuple(page for i, page in enumerate(pages, 1)
                          if any(r.from_ <= i <= r.to for r in ranges))
        else:
            first, last = printer.fromPage(), printer.toPage()
            pages = pages[max(1, first) - 1:last or len(pages)]
    if printer.pageOrder() == QPrinter.PageOrder.LastPageFirst:
        pages = pages[::-1]
    return pages


def printer_pages(printer, pages):
    """Apply native ranges/order/copies once, using positions in the print list."""
    pages = ordered_print_pages(printer, pages)
    if printer.pageOrder() == QPrinter.PageOrder.LastPageFirst:
        printer.setPageOrder(QPrinter.PageOrder.FirstPageFirst)
    if not printer.supportsMultipleCopies():
        copies = max(1, printer.copyCount())
        printer.setCopyCount(1)
        pages = pages * copies if printer.collateCopies() else tuple(p for p in pages for _ in range(copies))
    return pages


def print_rect(printer, width_points, height_points, scaling):
    layout = QPageLayout(printer.pageLayout())
    # Full-page painter coordinates must still respect the printer's margins.
    layout.setMode(QPageLayout.Mode.StandardMode)
    printable = QRectF(layout.paintRectPixels(printer.resolution()))
    width = width_points * printer.resolution() / 72
    height = height_points * printer.resolution() / 72
    scale = min(printable.width() / width, printable.height() / height) if scaling == 'fit' else 1
    width, height = width * scale, height * scale
    return printable, QRectF(printable.center().x() - width / 2,
                             printable.center().y() - height / 2, width, height)


class PrintJob(QObject):
    progress = Signal(int, int)
    finished = Signal(str, str)

    def __init__(self, printer, pages, scaling='fit', parent=None):
        super().__init__(parent)
        self.printer = printer
        self.pages = tuple(pages)
        self.scaling = scaling
        self.service = self.temp = self.painter = None
        self.index = 0
        self.ended = False
        self.rendered = False

    def start(self):
        if self.ended:
            return
        try:
            self.pages = printer_pages(self.printer, self.pages)
            if not self.pages:
                raise ValueError(tr('請至少選取一頁。'))
            self.printer.setFullPage(True)
            self.painter = QPainter()
            if not self.painter.begin(self.printer):
                raise RuntimeError(tr('無法開始列印，請檢查印表機設定。'))
            self.painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self.temp = tempfile.TemporaryDirectory(prefix='repdf-print-')
            self.service = RenderService(start_render_backend(), self)
            self.service.message.connect(self.receive)
            self.progress.emit(0, len(self.pages))
            if not self.ended:
                self.request_page()
        except Exception as exc:
            self.finish('failed', str(exc))

    def request_page(self):
        page = self.pages[self.index]
        self.rendered = False
        self.service.request_print(page.source, page.page, Path(self.temp.name), self.index + 1,
                                   password=page.password, annotation_changes=page.annotation_changes)

    def receive(self, payload):
        if self.ended or payload.get('generation') != self.index + 1:
            return
        try:
            kind = payload.get('type')
            if kind == 'error':
                raise RuntimeError(payload.get('message', tr('列印失敗')))
            if kind == 'page':
                if self.rendered:
                    raise RuntimeError(tr('列印頁面資料不完整。'))
                path = Path(payload['path'])
                image = QImage(str(path)).copy()
                path.unlink(missing_ok=True)
                if image.isNull():
                    raise RuntimeError(tr('無法讀取列印影像。'))
                if self.index and not self.printer.newPage():
                    raise RuntimeError(tr('無法建立下一張列印頁面。'))
                clip, target = print_rect(self.printer, payload['width_points'], payload['height_points'], self.scaling)
                self.painter.save()
                self.painter.setClipRect(clip)
                self.painter.drawImage(target, image)
                self.painter.restore()
                self.rendered = True
            elif kind == 'done':
                if not self.rendered:
                    raise RuntimeError(tr('列印頁面資料不完整。'))
                self.index += 1
                self.progress.emit(self.index, len(self.pages))
                if self.ended:
                    return
                if self.index == len(self.pages):
                    self.finish('completed')
                else:
                    self.request_page()
        except Exception as exc:
            self.finish('failed', str(exc))

    def cancel(self):
        self.finish('canceled')

    def finish(self, state, message=''):
        if self.ended:
            return
        self.ended = True
        if state != 'completed' and self.painter is not None and self.painter.isActive():
            self.printer.abort()
        if self.painter is not None and self.painter.isActive():
            if not self.painter.end() and state == 'completed':
                state, message = 'failed', tr('無法完成列印工作。')
        if self.service is not None:
            self.service.close(terminate_tree=True)
            self.service.deleteLater()
            self.service = None
        if self.temp is not None:
            self.temp.cleanup()
            self.temp = None
        self.pages = ()
        self.finished.emit(state, message)


class PrintController(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.job = self.progress_dialog = None
        self.preview = None
        self.opening = False

    @property
    def busy(self):
        return self.opening or self.job is not None

    def open(self):
        if hasattr(self.owner,"annotation_editor"):
            self.owner.annotation_editor.finish_text(True)
        doc = self.owner.current_document()
        if self.busy or doc is None or not doc.ready:
            return
        viewer = self.owner._fullscreen_preview
        current = viewer.page_index if viewer is not None else doc.preview_page_index()
        if viewer is not None:
            viewer.close()
        self.opening = True
        self.owner._sync_controls()
        options = preview = None
        try:
            options = PrintOptions(self.owner, doc, current)
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setDocName(doc.source_path.name)
            printer.setCreator('RePDF')
            from repdf.print_preview import PrintPreviewDialog
            preview = self.preview = PrintPreviewDialog(printer, options.pages,
                options.scaling.currentData(), self.owner, options=options)
            if preview.exec() == QDialog.DialogCode.Accepted and not self.owner._closing:
                self.start(printer, preview.accepted_pages, preview.scaling.currentData())
        except Exception as exc:
            QMessageBox.critical(self.owner, tr('列印失敗'), str(exc))
        finally:
            if preview is not None:
                preview.cleanup()
                preview.accepted_pages = ()
                preview.deleteLater()
                self.preview = None
            if options is not None:
                options.all_pages = options.selected_pages = options.pages = ()
                options.deleteLater()
            self.opening = False
            self.owner._sync_controls()

    def start(self, printer, pages, scaling):
        if self.job is not None:
            return
        self.job = PrintJob(printer, pages, scaling, self)
        self.progress_dialog = QProgressDialog(tr('正在準備列印…'), tr('取消'), 0, len(pages), self.owner)
        self.progress_dialog.setWindowTitle(tr('列印'))
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setAutoReset(False)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self.job.cancel)
        self.job.progress.connect(self.update_progress)
        self.job.finished.connect(self.finished)
        self.progress_dialog.show()
        self.owner._sync_controls()
        QTimer.singleShot(0, self.job.start)

    def update_progress(self, count, total):
        self.progress_dialog.setMaximum(total)
        self.progress_dialog.setValue(count)
        self.progress_dialog.setLabelText(tr('正在送印：{p0} / {p1} 頁', p0=count, p1=total))

    def finished(self, state, message):
        self.progress_dialog.close()
        self.progress_dialog.deleteLater()
        self.progress_dialog = None
        self.job.deleteLater()
        self.job = None
        self.owner._sync_controls()
        if self.owner._closing:
            return
        if state == 'failed':
            QMessageBox.critical(self.owner, tr('列印失敗'), message)
        self.owner.statusBar().showMessage(tr('列印工作已送出') if state == 'completed' else
            tr('已停止送印；已送出的頁面可能需要從系統列印佇列取消。') if state == 'canceled' else tr('列印失敗'))

    def close(self):
        if self.preview is not None:
            self.preview.reject()
        if self.job is not None:
            self.job.cancel()
