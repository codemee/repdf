import io
import json
from contextlib import closing

import pypdfium2 as pdfium
from pypdf import PdfWriter
from pypdf.constants import PageLabelStyle
from PySide6.QtCore import Qt

from repdf.app import MainWindow
from repdf.pdf_navigation import read_page_label, resolve_destination
from repdf.render_worker import render_document
from test_page_number import enter
from test_page_view import settled


def labeled_pdf(path, count=4, prefix='3-', password=None):
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(300, 400)
    writer.set_page_label(0, 1, style=PageLabelStyle.LOWERCASE_ROMAN, start=1)
    writer.set_page_label(2, count - 1, style=PageLabelStyle.DECIMAL, start=1)
    if count == 4:
        writer.set_page_label(3, 3, style=PageLabelStyle.DECIMAL, prefix=prefix, start=6)
    if password:
        writer.encrypt(password, algorithm='AES-256')
    writer.write(path)


def test_page_labels_are_read_on_demand_and_not_invented(tmp_path, monkeypatch):
    path = tmp_path / 'labels.pdf'
    labeled_pdf(path, prefix='附錄-', password='secret')
    with closing(pdfium.PdfDocument(str(path), password='secret')) as document:
        assert [read_page_label(document, i) for i in range(4)] == ['i', 'ii', '1', '附錄-6']
        destination = resolve_destination(document, {'page': 3})
        assert destination['page_label'] == '附錄-6'
        def fail(*args, **kwargs):
            raise AssertionError('Loading a page was unnecessary')
        with monkeypatch.context() as context:
            context.setattr(pdfium.PdfDocument, '__getitem__', fail)
            assert read_page_label(document, 0) == 'i'
    writer = PdfWriter()
    writer.add_blank_page(300, 400)
    writer.write(tmp_path / 'no-labels.pdf')
    with closing(pdfium.PdfDocument(str(tmp_path / 'no-labels.pdf'))) as document:
        assert read_page_label(document, 0) is None


def test_render_protocol_includes_only_requested_page_labels(tmp_path):
    path = tmp_path / 'labels.pdf'
    labeled_pdf(path)
    output = io.StringIO()
    render_document(path, 1, tmp_path, 42, output, pages=[1, 3])
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [(m['page'], m['page_label']) for m in messages] == [(1, 'ii'), (3, '3-6')]


def load_window(qtbot, path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    window.load_pdf(path)
    qtbot.waitUntil(lambda: window.current_document().ready, timeout=10000)
    doc = window.current_document()
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
    return window, doc


def test_status_label_keeps_original_page_input_and_survives_reorder(qtbot, tmp_path):
    path = tmp_path / '100-pages.pdf'
    labeled_pdf(path, count=100)
    window, doc = load_window(qtbot, path)
    assert window.book_page_label.isVisible()
    assert window.book_page_label.text() == '書頁 i｜'
    assert window.page_number_caption.text() == 'PDF'
    assert window.page_number_input.text() == '1'
    assert len(doc.page_labels) < 20
    enter(qtbot, window.page_number_input, '10')
    qtbot.keyClick(window.page_number_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: doc.focused_page == 9 and settled(doc), timeout=15000)
    assert window.book_page_label.text() == '書頁 8｜'
    assert window.page_number_input.text() == '10'
    doc._move_page(9, 0)
    enter(qtbot, window.page_number_input, '10')
    qtbot.keyClick(window.page_number_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
    assert doc.page_order[0] == 9
    assert window.book_page_label.text() == '書頁 8｜'
    assert window.page_number_input.text() == '10'
    assert doc.page_labels[0] == 'i'
    window.preview_cache.remove_document(doc.document_id)
    assert doc.page_labels[0] == 'i'
    window.close_tab(window.tabs.indexOf(doc))
    assert not window.book_page_label.isVisible()


def test_long_labels_narrow_layout_and_translation(qtbot, tmp_path):
    path = tmp_path / 'long-label.pdf'
    labeled_pdf(path, prefix='附錄<章節>&-' * 40)
    window, doc = load_window(qtbot, path)
    enter(qtbot, window.page_number_input, '4')
    qtbot.keyClick(window.page_number_input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: doc.focused_page == 3 and settled(doc), timeout=15000)
    window.resize(320, 240)
    qtbot.waitUntil(lambda: window.width() == 320)
    assert len(window.book_page_label.text()) < len(doc.page_labels[3])
    assert '&lt;' in window.book_page_label.toolTip()
    assert '&amp;' in window.book_page_label.toolTip()
    assert window.book_page_label.textFormat() == Qt.TextFormat.PlainText
    assert window.page_controls.width() < 320
    assert window.page_number_input.text() == '4'
    window.language_controller.set_mode('en')
    assert window.book_page_label.accessibleName().startswith('Book page ')
    assert window.page_number_input.text() == '4'
