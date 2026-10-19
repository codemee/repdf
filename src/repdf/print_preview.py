"""Lazy, paper-accurate preview before starting the print spooler."""

from collections import OrderedDict
from pathlib import Path
import tempfile

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QImage, QKeySequence, QPageLayout, QPageSize, QPainter, QPalette, QPen, QShortcut
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QToolButton, QVBoxLayout, QWidget)

from repdf.icons import toolbar_icon
from repdf.printing import ordered_print_pages, print_rect
from repdf.renderer import RenderService, start_render_backend
from repdf.strings import tr


class PaperPreview(QWidget):
    def __init__(self, printer, scaling):
        super().__init__()
        self.printer, self.scaling = printer, scaling
        self.image = QImage()
        self.points = None
        self.zoom = 0
        self.message = tr('正在產生列印預覽…')
        self.setMinimumSize(0, 0)

    def set_zoom(self, zoom):
        self.zoom = zoom
        paper = self.printer.pageLayout().fullRectPixels(96)
        self.setMinimumSize(round(paper.width() * zoom) + 32 if zoom else 0,
                            round(paper.height() * zoom) + 32 if zoom else 0)
        self.updateGeometry()
        self.update()

    def set_page(self, image, points=None, message=''):
        self.image = (image.convertToFormat(QImage.Format.Format_Grayscale8)
                      if self.printer.colorMode() == QPrinter.ColorMode.GrayScale else image)
        self.points = points
        self.message = message
        self.update()

    def paper_rect(self):
        paper = self.printer.pageLayout().fullRectPixels(self.printer.resolution())
        factor = max(.001, min(max(1, self.width() - 32) / paper.width(),
                               max(1, self.height() - 32) / paper.height()))
        if self.zoom:
            factor = 96 / self.printer.resolution() * self.zoom
        width, height = paper.width() * factor, paper.height() * factor
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().brush(QPalette.ColorRole.AlternateBase))
        paper = self.printer.pageLayout().fullRectPixels(self.printer.resolution())
        display = self.paper_rect()
        painter.fillRect(display, Qt.GlobalColor.white)
        painter.save()
        painter.translate(display.topLeft())
        factor = display.width() / paper.width()
        painter.scale(factor, factor)
        if self.points is not None:
            clip, target = print_rect(self.printer, *self.points, self.scaling)
            painter.save()
            painter.setClipRect(clip)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(target, self.image)
            painter.restore()
            painter.setPen(QPen(Qt.GlobalColor.lightGray, 1 / factor, Qt.PenStyle.DashLine))
            painter.drawRect(clip)
        painter.restore()
        if self.message:
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(display.adjusted(8, 8, -8, -8),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
        painter.end()


class PrintPreviewDialog(QDialog):
    def __init__(self, printer, pages, scaling='fit', parent=None, *, options=None):
        super().__init__(parent)
        self.printer = printer
        self.source_pages = tuple(pages)
        self.pages = ()
        self.cache = OrderedDict()
        self.service = self.temp = None
        self.generation = 0
        self.closed = False
        self.index = 0
        self.options = options
        self.accepted_pages = ()
        self.image_ready = False
        self.syncing = False
        self.setWindowTitle(tr('列印'))
        self.setMinimumSize(320, 420)
        self.resize(1060, 760)
        layout = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.panel = QWidget()
        self.panel.setMinimumSize(0, 0)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(4, 4, 4, 4)
        self.device_form = QFormLayout()
        self.device_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.printer_select = QComboBox()
        self.printer_select.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.printer_select.setMinimumContentsLength(15)
        if printer.outputFormat() == QPrinter.OutputFormat.PdfFormat:
            self.printer_select.addItem(tr('PDF 檔案'), None)
            self.printer_select.setEnabled(False)
        else:
            for info in QPrinterInfo.availablePrinters():
                self.printer_select.addItem(info.printerName(), info.printerName())
        if self.printer_select.count():
            self.printer_select.setCurrentIndex(max(0, self.printer_select.findData(printer.printerName())))
            if printer.outputFormat() == QPrinter.OutputFormat.NativeFormat and not printer.isValid():
                printer.setPrinterName(self.printer_select.currentData())
        else:
            self.printer_select.addItem(tr('沒有可用的印表機'), None)
            self.printer_select.setEnabled(False)
        self.device_form.addRow(tr('印表機'), self.printer_select)
        self.paper_select = QComboBox()
        self.device_form.addRow(tr('紙張'), self.paper_select)
        self.orientation = QComboBox()
        self.orientation.addItem(tr('直向'), QPageLayout.Orientation.Portrait)
        self.orientation.addItem(tr('橫向'), QPageLayout.Orientation.Landscape)
        self.device_form.addRow(tr('方向'), self.orientation)
        self.copies = QSpinBox()
        self.copies.setRange(1, 999)
        self.device_form.addRow(tr('份數'), self.copies)
        self.collate = QCheckBox(tr('逐份列印'))
        self.device_form.addRow(self.collate)
        self.duplex = QComboBox()
        self.device_form.addRow(tr('雙面列印'), self.duplex)
        self.color = QComboBox()
        self.device_form.addRow(tr('色彩'), self.color)
        panel_layout.addLayout(self.device_form)
        if options is not None:
            panel_layout.addWidget(options)
            self.scaling = options.scaling
        else:
            self.scaling = QComboBox()
            self.scaling.addItem(tr('符合可列印範圍'), 'fit')
            self.scaling.addItem(tr('實際大小'), 'actual')
            self.device_form.addRow(tr('縮放'), self.scaling)
        self.scaling.setCurrentIndex(self.scaling.findData(scaling))
        panel_layout.addStretch()
        self.panel_scroll = QScrollArea()
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setMinimumSize(0, 0)
        self.panel_scroll.setWidget(self.panel)
        self.splitter.addWidget(self.panel_scroll)
        self.preview_panel = QWidget()
        self.preview_panel.setMinimumSize(0, 0)
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        self.previous = self.tool('previous', '上一頁', lambda: self.show_page(self.index - 1))
        self.next = self.tool('next', '下一頁', lambda: self.show_page(self.index + 1))
        self.page_number = QSpinBox()
        self.page_number.setAccessibleName(tr('預覽頁次'))
        self.page_number.setKeyboardTracking(False)
        self.page_number.valueChanged.connect(lambda number: self.show_page(number - 1))
        self.total = QLabel()
        controls.addWidget(self.previous)
        controls.addWidget(self.page_number)
        controls.addWidget(self.total)
        controls.addWidget(self.next)
        controls.addStretch()
        self.zoom = QComboBox()
        self.zoom.setAccessibleName(tr('預覽縮放'))
        for text, value in ((tr('符合視窗'), 0), ('100%', 1), ('150%', 1.5), ('200%', 2)):
            self.zoom.addItem(text, value)
        preview_layout.addLayout(controls)
        self.page_info = QLabel()
        self.page_info.setWordWrap(True)
        self.page_info.setTextFormat(Qt.TextFormat.PlainText)
        self.page_info.setMinimumWidth(0)
        self.page_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        preview_layout.addWidget(self.page_info)
        options = QHBoxLayout()
        self.paper_info = QLabel()
        self.paper_info.setWordWrap(True)
        self.paper_info.setMinimumWidth(0)
        self.paper_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        options.addWidget(self.zoom)
        preview_layout.addLayout(options)
        preview_layout.addWidget(self.paper_info)
        self.canvas = PaperPreview(printer, scaling)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumSize(0, 0)
        self.scroll.setWidget(self.canvas)
        preview_layout.addWidget(self.scroll, 1)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        preview_layout.addWidget(self.status)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([300, 720])
        layout.addWidget(self.splitter, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.print_button = self.buttons.addButton(tr('列印'), QDialogButtonBox.ButtonRole.AcceptRole)
        self.print_button.setEnabled(False)
        self.printer_button = QPushButton(tr('進階設定'))
        self.printer_button.setToolTip(tr('開啟系統印表機設定；返回後按「列印」才送印。'))
        self.printer_button.clicked.connect(self.configure_printer)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(self.printer_button)
        bottom.addStretch()
        bottom.addWidget(self.buttons)
        layout.addLayout(bottom)
        self.zoom.currentIndexChanged.connect(lambda: self.canvas.set_zoom(self.zoom.currentData()))
        self.scaling.currentIndexChanged.connect(self.change_scaling)
        self.printer_select.currentIndexChanged.connect(self.change_printer)
        self.paper_select.currentIndexChanged.connect(self.change_paper)
        self.orientation.currentIndexChanged.connect(self.change_orientation)
        self.copies.valueChanged.connect(self.change_copies)
        self.collate.toggled.connect(lambda value: self.printer.setCollateCopies(value) if not self.syncing else None)
        self.duplex.currentIndexChanged.connect(self.change_duplex)
        self.color.currentIndexChanged.connect(self.change_color)
        if self.options is not None:
            self.options.selection_changed.connect(self.change_selection)
        for key, step in ((Qt.Key.Key_PageUp, -1), (Qt.Key.Key_PageDown, 1)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda delta=step: self.show_page(self.index + delta))
        self.sync_printer_controls()
        self.refresh_plan()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, 'next'):
            for button, icon in ((self.previous, 'previous'), (self.next, 'next')):
                button.setIcon(toolbar_icon(icon))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'splitter'):
            orientation = Qt.Orientation.Vertical if self.width() < 720 else Qt.Orientation.Horizontal
            if self.splitter.orientation() != orientation:
                self.splitter.setOrientation(orientation)
                self.splitter.setSizes([max(120, self.height() // 2), max(120, self.height() // 2)]
                    if orientation == Qt.Orientation.Vertical else [300, max(1, self.width() - 340)])

    def sync_printer_controls(self):
        self.syncing = True
        try:
            if self.printer.outputFormat() == QPrinter.OutputFormat.NativeFormat:
                names = [info.printerName() for info in QPrinterInfo.availablePrinters()]
                if self.printer.printerName() and self.printer.printerName() not in names:
                    names.insert(0, self.printer.printerName())
                self.printer_select.clear()
                for name in names:
                    self.printer_select.addItem(name, name)
                if not names:
                    self.printer_select.addItem(tr('沒有可用的印表機'), None)
                self.printer_select.setEnabled(bool(names))
            index = self.printer_select.findData(self.printer.printerName())
            if index >= 0:
                self.printer_select.setCurrentIndex(index)
            info = QPrinterInfo(self.printer) if self.printer.outputFormat() == QPrinter.OutputFormat.NativeFormat else QPrinterInfo()
            current = self.printer.pageLayout().pageSize()
            sizes = info.supportedPageSizes() or [QPageSize(value) for value in
                (QPageSize.PageSizeId.A4, QPageSize.PageSizeId.Letter, QPageSize.PageSizeId.A3,
                 QPageSize.PageSizeId.Legal, QPageSize.PageSizeId.A5)]
            if not any(size.isEquivalentTo(current) for size in sizes):
                sizes.insert(0, current)
            self.paper_select.clear()
            for size in sizes:
                self.paper_select.addItem(size.name(), size)
            self.paper_select.setCurrentIndex(next((i for i, size in enumerate(sizes) if size.isEquivalentTo(current)), 0))
            self.orientation.setCurrentIndex(self.orientation.findData(self.printer.pageLayout().orientation()))
            self.copies.setValue(self.printer.copyCount())
            self.collate.setChecked(self.printer.collateCopies())
            self.collate.setEnabled(self.printer.copyCount() > 1)
            duplex_modes = info.supportedDuplexModes() or [QPrinter.DuplexMode.DuplexNone]
            self.duplex.clear()
            for mode, text in ((QPrinter.DuplexMode.DuplexNone, '單面'), (QPrinter.DuplexMode.DuplexLongSide, '長邊翻頁'),
                               (QPrinter.DuplexMode.DuplexShortSide, '短邊翻頁'), (QPrinter.DuplexMode.DuplexAuto, '自動')):
                if mode in duplex_modes:
                    self.duplex.addItem(tr(text), mode)
            self.duplex.setCurrentIndex(max(0, self.duplex.findData(self.printer.duplex())))
            self.duplex.setEnabled(self.duplex.count() > 1)
            self.printer.setDuplex(self.duplex.currentData())
            color_modes = info.supportedColorModes() or [QPrinter.ColorMode.Color, QPrinter.ColorMode.GrayScale]
            self.color.clear()
            for mode, text in ((QPrinter.ColorMode.Color, '彩色'), (QPrinter.ColorMode.GrayScale, '黑白')):
                if mode in color_modes:
                    self.color.addItem(tr(text), mode)
            self.color.setCurrentIndex(max(0, self.color.findData(self.printer.colorMode())))
            self.color.setEnabled(self.color.count() > 1)
            self.printer.setColorMode(self.color.currentData())
            self.printer_button.setEnabled(self.printer.isValid() and self.printer.outputFormat() == QPrinter.OutputFormat.NativeFormat)
        finally:
            self.syncing = False

    def change_printer(self):
        if not self.syncing and self.printer_select.currentData():
            self.printer.setPrinterName(self.printer_select.currentData())
            self.sync_printer_controls()
            self.refresh_plan()

    def change_paper(self):
        if not self.syncing and self.paper_select.currentData() is not None:
            self.printer.setPageSize(self.paper_select.currentData())
            self.refresh_plan()

    def change_orientation(self):
        if not self.syncing:
            self.printer.setPageOrientation(self.orientation.currentData())
            self.refresh_plan()

    def change_copies(self, count):
        if not self.syncing:
            self.printer.setCopyCount(count)
            self.collate.setEnabled(count > 1)
            self.refresh_plan()

    def change_duplex(self):
        if not self.syncing and self.duplex.currentData() is not None:
            self.printer.setDuplex(self.duplex.currentData())

    def change_color(self):
        if not self.syncing:
            self.printer.setColorMode(self.color.currentData())
            self.refresh_plan()

    def change_selection(self):
        self.source_pages = tuple(self.options.pages)
        self.printer.setPrintRange(QPrinter.PrintRange.AllPages)
        self.refresh_plan()

    def enable_print(self, ready):
        self.image_ready = ready
        self.print_button.setEnabled(ready and bool(self.pages) and self.printer.isValid())
        if ready and not self.printer.isValid():
            self.status.setText(tr('沒有可用的印表機；可先預覽，設定印表機後才能列印。'))

    def tool(self, icon, text, callback):
        button = QToolButton()
        button.setFixedSize(34, 34)
        button.setIconSize(QSize(20, 20))
        button.setIcon(toolbar_icon(icon))
        button.setToolTip(tr(text))
        button.setAccessibleName(tr(text))
        button.clicked.connect(callback)
        return button

    def refresh_plan(self):
        previous = self.pages[self.index] if self.pages and self.index < len(self.pages) else None
        self.generation += 1
        if self.service is not None:
            self.service.cancel_pending('print')
        self.enable_print(False)
        self.canvas.set_page(QImage(), message=tr('正在產生列印預覽…'))
        self.pages = ordered_print_pages(self.printer, self.source_pages)
        self.index = self.pages.index(previous) if previous in self.pages else 0
        self.page_number.blockSignals(True)
        self.page_number.setRange(1, max(1, len(self.pages)))
        self.page_number.setValue(self.index + 1)
        self.page_number.setEnabled(bool(self.pages))
        self.page_number.blockSignals(False)
        self.total.setText(f'/ {len(self.pages)}')
        layout = self.printer.pageLayout()
        size = layout.fullRect(layout.Unit.Millimeter)
        self.paper_info.setText(tr('{p0} × {p1} mm；{p2} 份',
            p0=f'{size.width():g}', p1=f'{size.height():g}', p2=self.printer.copyCount()))
        self.printer_select.setToolTip(self.printer.printerName())
        self.canvas.set_zoom(self.zoom.currentData())
        QTimer.singleShot(0, lambda: self.show_page(self.index))

    def change_scaling(self):
        self.canvas.scaling = self.scaling.currentData()
        self.canvas.update()

    def configure_printer(self):
        dialog = QPrintDialog(self.printer, self)
        dialog.setMinMax(1, max(1, len(self.source_pages)))
        dialog.setOption(QPrintDialog.PrintDialogOption.PrintSelection, False)
        dialog.setOption(QPrintDialog.PrintDialogOption.PrintCurrentPage, False)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.sync_printer_controls()
            self.refresh_plan()
        dialog.deleteLater()

    def show_page(self, index):
        if self.closed:
            return
        if not self.pages:
            self.previous.setEnabled(False)
            self.next.setEnabled(False)
            self.enable_print(False)
            self.canvas.set_page(QImage(), message=tr('沒有可預覽的頁面。'))
            self.status.setText(tr('請至少選取一頁。'))
            return
        if not 0 <= index < len(self.pages):
            return
        self.index = index
        self.generation += 1
        if self.service is not None:
            self.service.cancel_pending('print')
        self.page_number.blockSignals(True)
        self.page_number.setValue(index + 1)
        self.page_number.blockSignals(False)
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(index + 1 < len(self.pages))
        page = self.pages[index]
        self.page_info.setText(tr('{p0}｜原始第 {p1} 頁', p0=page.source.name, p1=page.page + 1))
        self.page_info.setToolTip(str(page.source))
        self.status.setText(tr('預覽單份文件；虛線表示可列印範圍。'))
        if page in self.cache:
            self.cache.move_to_end(page)
            image, points = self.cache[page]
            self.canvas.set_page(image, points)
            self.enable_print(True)
            return
        self.enable_print(False)
        self.canvas.set_page(QImage(), message=tr('正在產生列印預覽…'))
        try:
            if self.service is None:
                self.temp = tempfile.TemporaryDirectory(prefix='repdf-print-preview-')
                self.service = RenderService(start_render_backend(), self)
                self.service.message.connect(self.receive)
            self.service.request_print(page.source, page.page, Path(self.temp.name), self.generation,
                                       password=page.password, preview=True)
        except Exception as exc:
            self.fail(str(exc))

    def receive(self, payload):
        if self.closed:
            return
        path = Path(payload['path']) if payload.get('type') == 'page' else None
        if payload.get('generation') != self.generation:
            if path is not None:
                path.unlink(missing_ok=True)
            return
        if path is not None:
            image = QImage(str(path)).copy()
            path.unlink(missing_ok=True)
            if image.isNull():
                self.fail(tr('無法讀取列印影像。'))
                return
            points = payload['width_points'], payload['height_points']
            self.cache[self.pages[self.index]] = image, points
            while len(self.cache) > 3:
                self.cache.popitem(last=False)
            self.canvas.set_page(image, points)
            self.enable_print(True)
        elif payload.get('type') == 'error':
            self.fail(payload.get('message', ''))

    def fail(self, message):
        self.enable_print(False)
        self.canvas.set_page(QImage(), message=tr('預覽無法載入'))
        self.status.setText(tr('無法產生列印預覽：{p0}', p0=message))

    def cleanup(self):
        if self.closed:
            return
        self.closed = True
        if self.service is not None:
            self.service.close(terminate_tree=True)
            self.service.deleteLater()
            self.service = None
        if self.temp is not None:
            self.temp.cleanup()
            self.temp = None
        self.cache.clear()
        self.pages = self.source_pages = ()
        if self.options is not None:
            self.options.all_pages = self.options.selected_pages = self.options.pages = ()
        self.canvas.set_page(QImage())

    def done(self, result):
        if result == QDialog.DialogCode.Accepted:
            if not self.print_button.isEnabled():
                return
            self.accepted_pages = self.source_pages
        self.cleanup()
        super().done(result)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
