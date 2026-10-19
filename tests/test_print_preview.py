from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QMarginsF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPageRanges, QPageSize
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QDialog

from repdf.print_preview import PrintPreviewDialog
from repdf.printing import PrintJob, PrintPage, print_rect
from repdf.renderer import RenderService
from test_printing import colored_pdf, pdf_printer
from test_navigation import load_window
from repdf.printing import PrintOptions


def ready(dialog):
    return dialog.print_button.isEnabled() and not dialog.canvas.image.isNull()


def test_preview_is_lazy_cached_and_matches_print_margins(qtbot, tmp_path, monkeypatch):
    source = tmp_path / 'secret.pdf'
    colored_pdf(source, 'secret')
    printer = pdf_printer(tmp_path / 'not-printed.pdf')
    calls = []
    original = RenderService.request_print
    def request(self, source, page, *args, **kwargs):
        calls.append((page, kwargs.get('preview')))
        return original(self, source, page, *args, **kwargs)
    monkeypatch.setattr(RenderService, 'request_print', request)
    pages = [PrintPage(source, i % 3, 'secret') for i in range(800)]
    dialog = PrintPreviewDialog(printer, pages)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: ready(dialog), timeout=15000)
    QCoreApplication.sendEvent(dialog.buttons, QEvent(QEvent.Type.LanguageChange))
    assert dialog.print_button.text() == '列印'
    assert calls == [(0, True)]
    assert not (tmp_path / 'not-printed.pdf').exists()
    assert dialog.canvas.image.width() * dialog.canvas.image.height() <= 4_000_000
    assert dialog.canvas.points == (200, 300)
    dialog.page_number.setValue(800)
    qtbot.waitUntil(lambda: dialog.index == 799 and ready(dialog), timeout=15000)
    assert calls == [(0, True), (1, True)]
    assert dialog.canvas.points == (300, 200)
    dialog.show_page(0)
    assert ready(dialog) and len(calls) == 2
    clip, actual = print_rect(printer, 200, 300, 'actual')
    dialog.scaling.setCurrentIndex(1)
    assert dialog.canvas.scaling == 'actual'
    assert actual.width() == 200
    assert clip.left() > 0
    dialog.zoom.setCurrentIndex(3)
    assert dialog.canvas.zoom == 2
    assert dialog.canvas.minimumHeight() > dialog.scroll.height()
    temp = Path(dialog.temp.name)
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not temp.exists() and dialog.service is None
    assert not dialog.pages and not dialog.cache
    source.unlink()


def test_preview_order_ranges_copies_are_not_consumed(qtbot, tmp_path):
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    printer = pdf_printer(tmp_path / 'printed.pdf')
    printer.setPrintRange(QPrinter.PrintRange.PageRange)
    ranges = QPageRanges()
    ranges.addRange(2, 3)
    printer.setPageRanges(ranges)
    printer.setPageOrder(QPrinter.PageOrder.LastPageFirst)
    printer.setCopyCount(2)
    printer.setCollateCopies(True)
    pages = [PrintPage(source, i) for i in (2, 0, 1)]
    dialog = PrintPreviewDialog(printer, pages)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: ready(dialog), timeout=15000)
    assert [p.page for p in dialog.pages] == [1, 0]
    assert printer.copyCount() == 2
    assert printer.pageOrder() == QPrinter.PageOrder.LastPageFirst
    dialog.accept()
    job = PrintJob(printer, pages)
    with qtbot.waitSignal(job.finished, timeout=30000) as result:
        job.start()
    assert result.args[0] == 'completed'
    from pypdf import PdfReader
    assert len(PdfReader(tmp_path / 'printed.pdf').pages) == 4


def test_refresh_printer_and_stale_messages_cannot_replace_current_page(qtbot, tmp_path, monkeypatch):
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    printer = pdf_printer(tmp_path / 'not-printed.pdf')
    dialog = PrintPreviewDialog(printer, [PrintPage(source, i) for i in range(3)])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: ready(dialog), timeout=15000)
    old_generation = dialog.generation
    dialog.show_page(2)
    qtbot.waitUntil(lambda: ready(dialog), timeout=15000)
    stale = tmp_path / 'stale.png'
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    image.save(str(stale))
    dialog.receive({'type': 'page', 'generation': old_generation, 'path': str(stale)})
    assert not stale.exists()
    assert dialog.canvas.points == (200, 300)
    assert dialog.index == 2
    monkeypatch.setattr('repdf.print_preview.QPrintDialog.exec', lambda self: QDialog.DialogCode.Accepted)
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
        QPageLayout.Orientation.Landscape, QMarginsF(20, 20, 20, 20)))
    printer.setColorMode(QPrinter.ColorMode.GrayScale)
    dialog.configure_printer()
    qtbot.waitUntil(lambda: dialog.index == 2 and ready(dialog), timeout=15000)
    assert dialog.canvas.image.format() == QImage.Format.Format_Grayscale8
    assert dialog.canvas.paper_rect().width() > dialog.canvas.paper_rect().height()
    assert '297' in dialog.paper_info.text()
    dialog.close()


def test_failed_preview_disables_print_and_cleans_up(qtbot, tmp_path):
    source = tmp_path / 'source.pdf'
    colored_pdf(source, 'secret')
    dialog = PrintPreviewDialog(pdf_printer(tmp_path / 'not-printed.pdf'), [PrintPage(source, 0, 'wrong')])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: '無法產生列印預覽' in dialog.status.text(), timeout=15000)
    assert not dialog.print_button.isEnabled()
    temp = Path(dialog.temp.name)
    dialog.close()
    assert not temp.exists()
    assert not (tmp_path / 'not-printed.pdf').exists()


def test_empty_preview_and_close_before_first_render(qtbot, tmp_path):
    dialog = PrintPreviewDialog(pdf_printer(tmp_path / 'not-printed.pdf'), [])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: bool(dialog.status.text()))
    assert not dialog.print_button.isEnabled()
    assert dialog.service is None
    dialog.close()


def test_integrated_options_update_paper_scope_and_preview_without_native_dialog(qtbot, tmp_path, monkeypatch):
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    window, doc = load_window(qtbot, source)
    doc._move_page(2, 0)
    options = PrintOptions(window, doc, 1)
    printer = pdf_printer(tmp_path / 'not-printed.pdf')
    dialog = PrintPreviewDialog(printer, options.pages, parent=window, options=options)
    qtbot.addWidget(dialog)
    monkeypatch.setattr('repdf.print_preview.QPrintDialog.exec', lambda self: (_ for _ in ()).throw(AssertionError('Unexpected native dialog')))
    dialog.show()
    qtbot.waitUntil(lambda: ready(dialog), timeout=15000)
    assert [p.page for p in dialog.pages] == [2, 0, 1]
    dialog.orientation.setCurrentIndex(1)
    qtbot.waitUntil(lambda: ready(dialog), timeout=15000)
    assert dialog.canvas.paper_rect().width() > dialog.canvas.paper_rect().height()
    letter = next(i for i in range(dialog.paper_select.count())
                  if dialog.paper_select.itemData(i).id() == QPageSize.PageSizeId.Letter)
    dialog.paper_select.setCurrentIndex(letter)
    assert printer.pageLayout().pageSize().id() == QPageSize.PageSizeId.Letter
    dialog.copies.setValue(3)
    dialog.collate.setChecked(True)
    assert printer.copyCount() == 3 and printer.collateCopies()
    dialog.color.setCurrentIndex(dialog.color.findData(QPrinter.ColorMode.GrayScale))
    qtbot.waitUntil(lambda: ready(dialog), timeout=15000)
    assert dialog.canvas.image.format() == QImage.Format.Format_Grayscale8
    options.scope.setCurrentIndex(2)
    qtbot.waitUntil(lambda: not dialog.print_button.isEnabled())
    assert not dialog.pages
    options.range_edit.setText('1,3')
    qtbot.waitUntil(lambda: ready(dialog), timeout=15000)
    assert [p.page for p in dialog.pages] == [2, 0]
    dialog.resize(320, 600)
    qtbot.waitUntil(lambda: dialog.width() == 320)
    assert dialog.splitter.orientation() == Qt.Orientation.Vertical
    dialog.accept()
    assert [p.page for p in dialog.accepted_pages] == [2, 0]
    assert not options.pages and not options.all_pages
    assert not (tmp_path / 'not-printed.pdf').exists()


def test_no_printer_still_allows_preview_without_sending(qtbot, tmp_path, monkeypatch):
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    monkeypatch.setattr('repdf.print_preview.QPrinterInfo.availablePrinters', lambda: [])
    printer = pdf_printer(tmp_path / 'not-printed.pdf')
    monkeypatch.setattr(printer, 'isValid', lambda: False)
    dialog = PrintPreviewDialog(printer, [PrintPage(source, 0)])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: not dialog.canvas.image.isNull(), timeout=15000)
    assert not dialog.print_button.isEnabled()
    assert not dialog.printer_button.isEnabled()
    assert not dialog.printer_select.isEnabled()
    assert '可先預覽' in dialog.status.text()
    dialog.accept()
    assert not dialog.closed  # Enter/accept cannot submit without a printer.
    dialog.reject()
    assert not (tmp_path / 'not-printed.pdf').exists()
