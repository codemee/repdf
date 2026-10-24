import io
import json
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from PySide6.QtCore import QMarginsF, Qt
from PySide6.QtGui import QImage, QKeySequence, QPageLayout, QPageRanges, QPageSize
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QDialog, QMessageBox

from repdf.printing import (PrintJob, PrintPage, PrintOptions, parse_page_range,
                            print_rect, printer_pages)
from repdf.render_worker import render_document
from test_navigation import load_window


def colored_pdf(path, password=None):
    writer = PdfWriter()
    for size, rgb in (((200, 300), '1 0 0'), ((300, 200), '0 0 1'), ((200, 300), '0 1 0')):
        page = writer.add_blank_page(*size)
        stream = DecodedStreamObject()
        stream.set_data(f'{rgb} rg 0 0 {size[0]} {size[1]} re f'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    if password:
        writer.encrypt(password, algorithm='AES-256')
    writer.write(path)


def pdf_printer(path):
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setResolution(72)
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
        QPageLayout.Orientation.Portrait, QMarginsF(10, 10, 10, 10)))
    return printer


@pytest.mark.parametrize('text', ['', '1,', '3-1', '0', '4', '-1', '1.2', '1,,2', '1-99999999999'])
def test_invalid_ranges(text):
    with pytest.raises(ValueError):
        parse_page_range(text, 3)


def test_ranges_deduplicate_and_preserve_visual_order(qtbot, tmp_path):
    assert parse_page_range(' 1, 3, 1-2 ', 3) == {0, 1, 2}
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    window, doc = load_window(qtbot, source)
    doc._move_page(2, 0)
    doc.selected_pages = {0, 2}
    settings = PrintOptions(window, doc, 1)
    qtbot.addWidget(settings)
    settings.show()
    settings.resize(340, settings.sizeHint().height())
    assert [p.page for p in settings.pages] == [2, 0, 1]
    assert settings.range_edit.isHidden()
    all_hint = settings.scope_hint.text()
    settings.scope.setCurrentIndex(1)
    assert [p.page for p in settings.pages] == [1]
    assert settings.scope_hint.text() != all_hint
    assert '2' in settings.scope_hint.text()
    settings.scope.setCurrentIndex(2)
    assert not settings.pages
    assert not settings.range_edit.isHidden()
    assert settings.summary.text() == ''
    settings.range_edit.setText('4')
    assert not settings.pages and settings.summary.text()
    settings.range_edit.setText('1,3,1')
    assert [p.page for p in settings.pages] == [2, 0]
    settings.scope.setCurrentIndex(3)
    assert [p.page for p in settings.pages] == [2, 0]
    assert settings.range_edit.isHidden()
    assert '目前標籤' in settings.scope_hint.text()
    fit_hint = settings.scaling_hint.text()
    settings.scaling.setCurrentIndex(1)
    assert settings.scaling_hint.text() != fit_hint
    assert '裁切' in settings.scaling_hint.text()
    qtbot.waitUntil(lambda: settings.scaling_hint.height() >= settings.scaling_hint.heightForWidth(settings.scaling_hint.width()))
    settings.scaling.setCurrentIndex(0)
    assert settings.scaling_hint.text() == fit_hint
    second = tmp_path / 'other.pdf'
    colored_pdf(second)
    window.load_pdf(second)
    qtbot.waitUntil(lambda: window.current_document().ready, timeout=10000)
    other = window.current_document()
    other.selected_pages = {1}
    doc.include_checkbox.setChecked(True)
    other.include_checkbox.setChecked(True)
    settings2 = PrintOptions(window, other, 0)
    qtbot.addWidget(settings2)
    settings2.scope.setCurrentIndex(3)
    assert '已勾選標籤' in settings2.scope_hint.text()
    assert [(p.source, p.page) for p in settings2.pages] == [(source, 2), (source, 0), (second, 1)]
    doc.selected_pages.clear()
    assert len(settings2.pages) == 3  # Immutable snapshot.


def test_native_ranges_copy_order_and_scaling(qtbot, tmp_path):
    printer = pdf_printer(tmp_path / 'range.pdf')
    pages = tuple(PrintPage(tmp_path / 'source.pdf', i) for i in range(4))
    printer.setPrintRange(QPrinter.PrintRange.PageRange)
    ranges = QPageRanges()
    ranges.addPage(1)
    ranges.addRange(3, 4)
    printer.setPageRanges(ranges)
    printer.setPageOrder(QPrinter.PageOrder.LastPageFirst)
    printer.setCopyCount(2)
    printer.setCollateCopies(True)
    assert [p.page for p in printer_pages(printer, pages)] == [3, 2, 0] * 2
    assert printer.copyCount() == 1
    printer.setFullPage(True)
    clip, fit = print_rect(printer, 1000, 500, 'fit')
    assert clip.left() > 0 and clip.top() > 0
    _, actual = print_rect(printer, 1000, 500, 'actual')
    assert fit.center() == clip.center() == actual.center()
    assert fit.width() == pytest.approx(clip.width())
    assert fit.width() / fit.height() == 2
    assert actual.width() == 1000


def test_job_prints_original_pages_in_order_with_password(qtbot, tmp_path):
    import pypdfium2 as pdfium
    source, output = tmp_path / 'source.pdf', tmp_path / 'printed.pdf'
    colored_pdf(source, 'secret')
    printer = pdf_printer(output)
    job = PrintJob(printer, [PrintPage(source, i, 'secret') for i in (2, 0, 1)])
    progress = []
    temp_paths = []
    job.progress.connect(lambda n, total: (progress.append((n, total)),
                         temp_paths.append(job.temp.name) if job.temp else None))
    with qtbot.waitSignal(job.finished, timeout=30000) as result:
        job.start()
    assert result.args == ['completed', '']
    assert progress == [(i, 3) for i in range(4)]
    assert not job.pages and job.service is None
    assert all(not Path(path).exists() for path in temp_paths)
    assert len(PdfReader(output).pages) == 3
    document = pdfium.PdfDocument(output)
    try:
        for i, expected in enumerate(((0, 255, 0), (255, 0, 0), (0, 0, 255))):
            page = document[i]
            bitmap = page.render(scale=.25)
            try:
                image = bitmap.to_pil().convert('RGB')
                actual = image.getpixel((image.width // 2, image.height // 2))
                assert actual == pytest.approx(expected, abs=3)
                assert image.getpixel((image.width // 2, 1)) == (255, 255, 255)
            finally:
                bitmap.close()
                page.close()
    finally:
        document.close()


def test_cancel_stops_backend_before_cleanup_and_future_pages(qtbot, tmp_path):
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    job = PrintJob(pdf_printer(tmp_path / 'canceled.pdf'), [PrintPage(source, i % 3) for i in range(800)])
    paths, states = [], []
    def progress(count, total):
        paths.append(job.temp.name)
        if count == 1:
            job.cancel()
    job.progress.connect(progress)
    job.finished.connect(lambda state, _message: states.append(state))
    with qtbot.waitSignal(job.finished, timeout=15000):
        job.start()
    assert states == ['canceled']
    assert job.index == 1
    assert all(not Path(path).exists() for path in paths)
    job.cancel()
    job.start()
    assert states == ['canceled']


def test_failure_releases_backend_and_pdf(qtbot, tmp_path):
    source = tmp_path / 'source.pdf'
    colored_pdf(source, 'secret')
    job = PrintJob(pdf_printer(tmp_path / 'failed.pdf'), [PrintPage(source, 0, 'wrong')])
    with qtbot.waitSignal(job.finished, timeout=15000) as result:
        job.start()
    assert result.args[0] == 'failed'
    assert result.args[1]
    assert job.service is None and job.temp is None and not job.pages
    source.unlink()  # No leaked source-file handle on Windows.


def test_print_resolution_cap_and_requested_page(tmp_path):
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    output = io.StringIO()
    render_document(source, 300 / 72, tmp_path, 1, output, pages=[1], max_pixels=10000)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [m['page'] for m in messages] == [1]
    image = QImage(messages[0]['path'])
    assert image.width() * image.height() <= 10000


def test_shortcuts_fullscreen_overflow_and_settings_cancel(qtbot, tmp_path, monkeypatch):
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    window, doc = load_window(qtbot, source)
    assert window.print_action.isEnabled()
    assert window.print_action.shortcuts() == QKeySequence.keyBindings(QKeySequence.StandardKey.Print)
    invoked = []
    monkeypatch.setattr(window.print_controller, 'open', lambda: invoked.append(True))
    window.print_action.trigger()
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    qtbot.waitUntil(viewer.isActiveWindow)
    key = window.print_action.shortcuts()[0][0]
    qtbot.keyClick(viewer, key.key(), key.keyboardModifiers())
    assert len(invoked) == 2
    viewer.close()
    window.resize(320, 240)
    qtbot.waitUntil(lambda: window.width() == 320)
    assert window.toolbar.widgetForAction(window.print_action).size().width() == 34
    assert not window.print_action.icon().isNull()


def test_single_print_window_does_not_open_native_dialog(qtbot, tmp_path, monkeypatch):
    import repdf.printing as printing
    from repdf.print_preview import PrintPreviewDialog
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    window, doc = load_window(qtbot, source)
    monkeypatch.setattr(printing, 'start_render_backend', lambda: pytest.fail('Unexpected print backend'))
    monkeypatch.setattr('repdf.print_preview.QPrintDialog.exec', lambda self: pytest.fail('Unexpected system dialog'))
    monkeypatch.setattr(PrintPreviewDialog, 'exec', lambda self: QDialog.DialogCode.Rejected)
    window.print_controller.open()
    assert window.print_action.isEnabled() and not window.print_controller.busy
    captured = []
    monkeypatch.setattr(window.print_controller, 'start', lambda printer, pages, scaling: captured.append((pages, scaling)))
    def confirm(dialog):
        assert QKeySequence(Qt.Key.Key_PageUp).toString(QKeySequence.SequenceFormat.NativeText) in dialog.previous.toolTip()
        assert QKeySequence(Qt.Key.Key_PageDown).toString(QKeySequence.SequenceFormat.NativeText) in dialog.next.toolTip()
        dialog.options.scope.setCurrentIndex(2)
        dialog.options.range_edit.setText('1,3')
        dialog.scaling.setCurrentIndex(1)
        dialog.accepted_pages = dialog.source_pages
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(PrintPreviewDialog, 'exec', confirm)
    window.print_controller.open()
    assert [p.page for p in captured[0][0]] == [0, 2]
    assert captured[0][1] == 'actual'
    assert window.print_action.isEnabled()


def test_controller_cancels_on_window_close_and_disables_second_job(qtbot, tmp_path):
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    window, doc = load_window(qtbot, source)
    controller = window.print_controller
    pages = [PrintPage(source, i % 3) for i in range(100)]
    controller.start(pdf_printer(tmp_path / 'closed.pdf'), pages, 'fit')
    job = controller.job
    assert not window.print_action.isEnabled()
    controller.start(pdf_printer(tmp_path / 'second.pdf'), pages, 'fit')
    assert controller.job is job
    qtbot.waitUntil(lambda: job.temp is not None, timeout=10000)
    temp_path = Path(job.temp.name)
    window.close()
    assert controller.job is None and job.ended
    assert not temp_path.exists()


def test_native_uncollated_copies_and_failed_printer(qtbot, tmp_path, monkeypatch):
    printer = pdf_printer(tmp_path / 'uncollated.pdf')
    printer.setCopyCount(2)
    printer.setCollateCopies(False)
    pages = [PrintPage(tmp_path / 'source.pdf', i) for i in range(2)]
    assert [p.page for p in printer_pages(printer, pages)] == [0, 0, 1, 1]
    job = PrintJob(pdf_printer(tmp_path / 'missing' / 'not-created.pdf'), pages)
    with qtbot.waitSignal(job.finished) as result:
        job.start()
    assert result.args[0] == 'failed'
    assert job.service is None and job.temp is None and not job.pages
