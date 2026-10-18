import io
import json
from contextlib import closing

import pytest
import pypdfium2 as pdfium
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage

from repdf.app import DocumentView, MainWindow
from repdf.search import compile_query, search_page


def test_sidebar_icon_buttons_and_single_line_results(qtbot):
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QListWidgetItem
    from repdf.search_panel import ParagraphDelegate, SearchPanel

    panel = SearchPanel()
    qtbot.addWidget(panel)
    panel.resize(320, 420)
    panel.show()
    for button in (panel.search_button, panel.stop_button, panel.close_button, panel.compact_options,
                   panel.regular_expression, panel.case_sensitive, panel.whole_word):
        assert button.size() == QSize(34, 34)
        assert button.iconSize() == QSize(20, 20)
        assert not button.icon().isNull()
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert button.toolTip() and button.accessibleName()
    assert not panel.paragraphs.wordWrap()
    assert panel.paragraphs.alternatingRowColors()
    text = 'A long matching paragraph\nwith complete text retained for navigation. ' * 10
    for _ in range(3):
        panel.paragraphs.addItem(QListWidgetItem(text))
    qtbot.wait(30)
    assert panel.scope.geometry().center().y() == panel.regular_expression.geometry().center().y()
    assert panel.regular_expression.geometry().top() == panel.case_sensitive.geometry().top()
    actions = panel.compact_options.menu().actions()
    for button, action in zip((panel.regular_expression, panel.case_sensitive, panel.whole_word), actions[1:]):
        assert button.isCheckable() and not button.isChecked()
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert button.isChecked() and action.isChecked()
        action.trigger()
        assert not button.isChecked()
    rect = panel.paragraphs.visualItemRect(panel.paragraphs.item(0))
    assert rect.height() == panel.paragraphs.fontMetrics().height() + 10
    metrics = panel.paragraphs.fontMetrics()
    clipped = ParagraphDelegate.elided_text(text, metrics, 180)
    assert clipped.endswith('...') and '\n' not in clipped
    assert metrics.horizontalAdvance(clipped) <= 180
    assert ParagraphDelegate.elided_text('short\ntext', metrics, 180) == 'short text'
    assert panel.paragraphs.item(0).text() == text


def search_pdf(path, pages=None, rotation=0, crop=False):
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    font_ref = writer._add_object(font)
    for lines in pages or [[(40, 340, 'Copy this text copy'), (40, 318, 'and this line'),
                            (40, 220, 'Another paragraph copy')]]:
        page = writer.add_blank_page(300, 400)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref})})
        commands = []
        for x, y, text in lines:
            text = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            commands.append(f'BT /F1 14 Tf {x} {y} Td ({text}) Tj ET')
        stream = DecodedStreamObject()
        stream.set_data('\n'.join(commands).encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
        if rotation:
            page.rotate(rotation)
        if crop:
            page.cropbox.lower_left = (20, 20)
            page.cropbox.upper_right = (280, 380)
    writer.write(path)


def results(path, query, regex=False, case=False, whole_word=False):
    with closing(pdfium.PdfDocument(str(path))) as pdf:
        with closing(pdf[0]) as page:
            return search_page(page, compile_query(query, regex, case, whole_word))


def test_whole_word_unicode_case_and_regex():
    text = 'cat Cat catalog scatter cat_ cat2 2cat écat caté cat\u0301 (cat)'
    pattern = compile_query('cat', whole_word=True)
    assert [m.group() for m in pattern.finditer(text)] == ['cat', 'Cat', 'cat']
    assert len(list(compile_query('cat', case_sensitive=True, whole_word=True).finditer(text))) == 2
    assert [m.group() for m in compile_query('cat|dog', True, whole_word=True).finditer('cats cat dog dogma')] == ['cat', 'dog']
    assert compile_query('中文', whole_word=True).search('這是中文') is None
    assert compile_query('中文', whole_word=True).search('中文。')
    assert compile_query('C++', whole_word=True).search('C++ guide')
    assert compile_query('(?x) cat # comment', True, whole_word=True).search('cat')
    assert not compile_query('(?x) cat # comment', True, whole_word=True).search('catalog')


def test_whole_word_backend_and_ui_option(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    path = tmp_path / 'words.pdf'
    search_pdf(path, [[(20, 340, 'cat catalog scatter cat_ cat2 Cat')]])
    assert sum(p['count'] for p in results(path, 'cat', whole_word=True)[0]) == 2
    window = MainWindow()
    qtbot.addWidget(window)
    loaded_document(window, path)
    c = window.search_controller
    c.panel.query.setText('cat')
    c.panel.whole_word.setChecked(True)
    c.start()
    wait_search(qtbot, c)
    assert c.params['whole_word']
    paragraphs = c.results[c.order[0]][0]
    assert sum(p['count'] for p in paragraphs) == 2
    c.panel.whole_word.setChecked(False)
    c.start()
    wait_search(qtbot, c)
    assert sum(p['count'] for p in c.results[c.order[0]][0]) == 6


def test_literal_case_regex_and_paragraph_grouping(tmp_path):
    path = tmp_path / 'text.pdf'
    search_pdf(path)
    hits, _ = results(path, 'copy')
    assert len(hits) == 2
    assert hits[0]['count'] == 2
    assert hits[1]['count'] == 1
    assert 'and this line' in hits[0]['text']
    assert sum(hit['count'] for hit in results(path, 'Copy', case=True)[0]) == 1
    assert sum(hit['count'] for hit in results(path, r'c.py', regex=True)[0]) == 3
    assert results(path, 'c.py')[0] == []
    assert results(path, r'^', regex=True)[0] == []
    assert results(path, r'^', regex=True)[1] == 2
    assert results(path, 'copy and this')[0]
    assert not results(path, 'line Another')[0]
    with pytest.raises(Exception):
        compile_query('(', True)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_search_rectangles_follow_rotation_and_crop(tmp_path, rotation):
    path = tmp_path / 'text.pdf'
    search_pdf(path, rotation=rotation, crop=True)
    hits, _ = results(path, 'Copy', case=True)
    assert len(hits) == 1
    rect = hits[0]['rects'][0]
    assert all(0 <= value <= 1 for value in rect)
    assert rect[0] < rect[2] and rect[1] < rect[3]
    # Original first letter is at x≈40, y≈340 (near the top left).
    if rotation == 0:
        assert rect[0] < .2 and rect[1] < .2
    elif rotation == 90:
        assert rect[0] > .8 and rect[1] < .2
    elif rotation == 180:
        assert rect[0] > .8 and rect[1] > .8
    else:
        assert rect[0] < .2 and rect[1] > .8


def test_columns_do_not_merge_and_query_stays_on_page(tmp_path):
    path = tmp_path / 'columns.pdf'
    search_pdf(path, [[(20, 340, 'Left copy'), (180, 340, 'Right copy'),
                       (20, 318, 'continues'), (180, 318, 'continues')]])
    hits, _ = results(path, 'copy')
    assert len(hits) == 2
    assert hits[0]['text'] == 'Left copy continues'
    assert hits[1]['text'] == 'Right copy continues'


def test_search_protocol_password_failure_and_timeout(tmp_path, monkeypatch):
    from repdf import render_worker
    path, locked = tmp_path / 'text.pdf', tmp_path / 'locked.pdf'
    search_pdf(path)
    writer = PdfWriter(clone_from=path)
    writer.encrypt('search-secret', algorithm='AES-256')
    writer.write(locked)
    request = {'type': 'search', 'source': str(locked), 'password': 'search-secret',
               'query': 'copy', 'regular_expression': False, 'case_sensitive': False,
               'document_id': 123, 'generation': 1, 'pages': [0]}
    output = io.StringIO()
    render_worker.serve(io.StringIO(json.dumps(request)), output)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [m['type'] for m in messages] == ['ready', 'search_page', 'done']
    assert len(messages[1]['paragraphs']) == 2
    assert 'search-secret' not in output.getvalue()
    def timed_out(*_args):
        raise TimeoutError('search timed out')
    monkeypatch.setattr('repdf.search.search_page', timed_out)
    output = io.StringIO()
    render_worker.serve(io.StringIO(json.dumps(request)), output)
    message = json.loads(output.getvalue().splitlines()[-1])
    assert message['type'] == 'error' and message['timeout']
    assert message['document_id'] == 123


def loaded_document(window, path, count=1):
    doc = window._new_document(path)
    doc.loaded(count)
    image = QImage(300, 400, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    for card in doc.page_cards:
        card.set_image(image)
        doc.page_sizes[card.page_index] = (300, 400)
    window._sync_controls()
    return doc


def wait_search(qtbot, controller):
    qtbot.waitUntil(lambda: not controller.pending, timeout=10000)


def test_scope_results_navigation_highlights_and_narrow_layout(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    a, b = tmp_path / 'a.pdf', tmp_path / 'b.pdf'
    search_pdf(a)
    search_pdf(b, [[(40, 340, 'Nothing here')], [(40, 340, 'copy once')]])
    window = MainWindow()
    qtbot.addWidget(window)
    doc_a, doc_b = loaded_document(window, a), loaded_document(window, b, 2)
    window.show()
    c = window.search_controller
    window.search_action.trigger()
    assert c.panel.isVisible()
    c.panel.query.setText('copy')
    c.start()
    wait_search(qtbot, c)
    assert c.panel.files.count() == 1
    assert c.panel.files.item(0).data(Qt.ItemDataRole.UserRole) == doc_b.document_id
    c.panel.scope.setCurrentIndex(1)
    c.start()
    assert not c.pending
    assert c.panel.files.count() == 0
    doc_a.include_checkbox.setChecked(True)
    c.start()
    wait_search(qtbot, c)
    assert c.panel.files.count() == 1
    assert c.panel.paragraphs.count() == 2
    assert c.panel.files.item(0).data(Qt.ItemDataRole.UserRole) == doc_a.document_id
    item = c.panel.paragraphs.item(0)
    c._activate_item(item)
    assert window.current_document() is doc_a
    label = doc_a.page_cards[0].preview
    assert len(label._search_rects) > len(label._active_search_rects)
    assert label._active_search_rects
    window.region_ocr_action.setChecked(True)
    assert label._active_search_rects
    c.panel.scope.setCurrentIndex(2)
    c.start()
    wait_search(qtbot, c)
    assert c.panel.files.count() == 2
    assert c.service.process.pid != window.render_service.process.pid
    c.panel.files.setCurrentRow(1)
    assert c.panel.paragraphs.count() == 1
    window.region_ocr_action.setChecked(False)
    doc_b._move_page(1, 0)
    assert doc_b.page_order == [1, 0]
    window.resize(320, 240)
    qtbot.waitUntil(lambda: window.width() == 320 and window.height() == 240)
    assert c.panel.isVisible() and not c.content.isVisible()
    assert c.panel.compact_options.isVisible()
    assert not c.panel.scope.isVisible()
    c._activate_item(c.panel.paragraphs.item(0))
    assert c.content.isVisible() and not c.panel.isVisible()
    assert window.current_document() is doc_b
    assert doc_b.focused_page == 1
    c.open()
    assert c.panel.isVisible() and c.panel.paragraphs.count() == 1
    c.close()
    assert not doc_b.page_cards[1].preview._search_rects
    assert c.content.isVisible()


def test_cancel_stale_results_invalid_regex_close_and_keyboard(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    path = tmp_path / 'a.pdf'
    search_pdf(path)
    window = MainWindow()
    qtbot.addWidget(window)
    doc = loaded_document(window, path)
    window.show()
    c = window.search_controller
    c.open()
    c.panel.query.setText('copy')
    c.start()
    old_generation = c.generation
    c.stop()
    c._receive({'type': 'search_page', 'generation': old_generation, 'document_id': doc.document_id,
                'page': 0, 'paragraphs': [{'text': 'stale'}]})
    assert c.results == {}
    c.panel.regular_expression.setChecked(True)
    c.panel.query.setText('(')
    c.start()
    assert not c.pending and '無效' in c.panel.status.text()
    c.panel.query.setText('copy')
    c.panel.query.setFocus()
    qtbot.keyClick(c.panel.query, Qt.Key.Key_Home)
    assert c.panel.query.cursorPosition() == 0
    qtbot.keyClick(c.panel.query, Qt.Key.Key_Return)
    wait_search(qtbot, c)
    assert c.panel.files.count() == 1
    window.close_tab(window.tabs.indexOf(doc))
    assert not c.results and c.panel.files.count() == 0


def test_unicode_wrap_and_raw_character_index_mapping(monkeypatch):
    import pypdfium2.raw as raw
    text = '𠀀中文\n搜尋\x00B'
    class TextPage:
        def close(self):
            pass
        def count_chars(self):
            return len(text)
        def get_charbox(self, index):
            row = int(index > 3)
            column = index if not row else index - 4
            return (40 + column * 12, 300 - row * 22, 50 + column * 12, 312 - row * 22)
    class Page:
        def get_textpage(self):
            return TextPage()
        def get_bbox(self):
            return (0, 0, 300, 400)
        def get_rotation(self):
            return 0
    monkeypatch.setattr(raw, 'FPDFText_GetUnicode', lambda _page, index: ord(text[index]))
    hits, _ = search_page(Page(), compile_query('文搜'))
    assert hits[0]['text'] == '𠀀中文搜尋B'
    assert len(hits[0]['rects']) == 2
    assert hits[0]['rects'][0][1] < hits[0]['rects'][1][1]
    hits, _ = search_page(Page(), compile_query('B'))
    assert hits[0]['rects'][0][0] == pytest.approx(76 / 300)


def test_actual_regex_matching_has_a_time_limit(monkeypatch):
    import repdf.search as search
    class TextPage:
        def close(self):
            pass
    class Page:
        def get_textpage(self):
            return TextPage()
    monkeypatch.setattr(search, '_lines', lambda _: [
        {'entries': [(char, (0, 0, 1, 1)) for char in 'a' * 1000 + '!'],
         'bounds': (0, 0, 100, 10), 'section': 0}])
    with pytest.raises(TimeoutError):
        search.search_page(Page(), compile_query('(a|aa)+$', True))


def test_one_file_error_and_closing_pending_file_keep_other_results(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    a, b = tmp_path / 'a.pdf', tmp_path / 'b.pdf'
    search_pdf(a)
    search_pdf(b)
    window = MainWindow()
    qtbot.addWidget(window)
    doc_a = loaded_document(window, a)
    doc_b = loaded_document(window, b)
    bad = loaded_document(window, tmp_path / 'missing.pdf')
    c = window.search_controller
    c.open()
    c.panel.scope.setCurrentIndex(2)
    c.panel.query.setText('copy')
    c.start()
    wait_search(qtbot, c)
    assert bad.document_id in c.failures
    assert c.panel.files.count() == 2
    assert '不完整' in c.panel.status.text()
    window.close_tab(window.tabs.indexOf(bad))
    c.start()
    assert doc_a.document_id in c.pending
    window.close_tab(window.tabs.indexOf(doc_a))
    wait_search(qtbot, c)
    assert list(c.results) == [doc_b.document_id]
    assert c.panel.files.count() == 1


def test_search_highlight_is_independent_and_persists_through_zoom(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    path = tmp_path / 'a.pdf'
    search_pdf(path)
    window = MainWindow()
    qtbot.addWidget(window)
    doc = loaded_document(window, path)
    window.show()
    c = window.search_controller
    c.open()
    c.panel.query.setText('copy')
    c.start()
    wait_search(qtbot, c)
    c._activate_item(c.panel.paragraphs.item(0))
    label = doc.page_cards[0].preview
    assert not label.text_mode
    rect = label._active_search_rects[0]
    color = label.grab().toImage().pixelColor(round((rect[0] + rect[2]) / 2 * label.width()),
                                            round((rect[1] + rect[3]) / 2 * label.height()))
    assert color.red() > 200 and color.blue() < 200
    expected = list(label._active_search_rects)
    doc.page_cards[0].set_target_width(500)
    assert label._active_search_rects == expected
    window._theme_controller.set_mode('dark')
    assert label._active_search_rects == expected
    c.panel.paragraphs.setCurrentRow(0)
    c._refresh_files()
    assert c.panel.paragraphs.currentRow() == 0


def test_find_shortcut_fullscreen_and_compact_options(qtbot, tmp_path, monkeypatch):
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    path = tmp_path / 'a.pdf'
    search_pdf(path)
    window = MainWindow()
    qtbot.addWidget(window)
    loaded_document(window, path)
    window.show()
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    c = window.search_controller
    shortcut = QKeySequence.keyBindings(QKeySequence.StandardKey.Find)[0]
    QTest.keySequence(window, shortcut)
    assert c.panel.isVisible()
    c.close()
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    qtbot.waitExposed(viewer)
    viewer.activateWindow()
    QTest.keySequence(viewer, shortcut)
    qtbot.waitUntil(lambda: window._fullscreen_preview is None and c.panel.isVisible())
    window.resize(320, 240)
    qtbot.waitUntil(c.panel.compact_options.isVisible)
    c.panel.scope_actions[2].trigger()
    assert c.panel.scope.currentIndex() == 2
    actions = c.panel.compact_options.menu().actions()
    actions[1].trigger()
    actions[2].trigger()
    assert c.panel.regular_expression.isChecked()
    assert c.panel.case_sensitive.isChecked()
    assert not c.pending  # Changing conditions alone never starts a search.


def test_search_uses_each_documents_password_and_disambiguates_names(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    plain = tmp_path / 'source.pdf'
    search_pdf(plain)
    window = MainWindow()
    qtbot.addWidget(window)
    for folder, password in (('one', 'first-secret'), ('two', 'second-secret')):
        directory = tmp_path / folder
        directory.mkdir()
        path = directory / 'same.pdf'
        writer = PdfWriter(clone_from=plain)
        writer.encrypt(password, algorithm='AES-256')
        writer.write(path)
        doc = loaded_document(window, path)
        doc.password = password
    c = window.search_controller
    c.panel.scope.setCurrentIndex(2)
    c.panel.query.setText('copy')
    c.start()
    wait_search(qtbot, c)
    assert not c.failures
    assert c.panel.files.count() == 2
    assert c.panel.files.item(0).toolTip() != c.panel.files.item(1).toolTip()
    assert len(c.results) == 2


def test_search_opens_from_overflow_and_focuses_query(qtbot):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from repdf.app import configure_application
    configure_application(QApplication.instance())
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    window.resize(320, 500)
    qtbot.waitUntil(lambda: window.width() == 320)
    toolbar = window.toolbar
    qtbot.waitUntil(toolbar.overflow_button.isVisible)
    def choose_search():
        toolbar.overflow_menu.setActiveAction(window.search_action)
        qtbot.keyClick(toolbar.overflow_menu, Qt.Key.Key_Return)
    QTimer.singleShot(100, choose_search)
    qtbot.mouseClick(toolbar.overflow_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(window.search_controller.panel.query.hasFocus)
    assert window.search_controller.panel.isVisible()
