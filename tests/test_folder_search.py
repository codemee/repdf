from pathlib import Path

from PySide6.QtCore import Qt
from pypdf import PdfWriter

from test_navigation import load_window
from test_page_view import settled
from test_search import search_pdf, wait_search


def test_folder_search_opens_only_selected_results_and_reuses_tabs(qtbot, tmp_path):
    first, unopened = tmp_path / 'a.pdf', tmp_path / 'b.PDF'
    search_pdf(first, [[(40, 300, 'target first')]])
    search_pdf(unopened, [[(40, 300, 'nothing')], [(40, 300, 'target second')]])
    subfolder = tmp_path / 'subfolder'
    subfolder.mkdir()
    search_pdf(subfolder / 'ignored.pdf', [[(40, 300, 'target nested')]])
    (tmp_path / 'ignored.txt').write_text('target', encoding='utf-8')
    window, doc = load_window(qtbot, first)
    controller = window.search_controller
    controller.open()
    controller.panel.scope.setCurrentIndex(3)
    controller.panel.query.setText('target')
    controller.start()
    wait_search(qtbot, controller)
    assert window.tabs.count() == 1
    assert {target.source_path for target in controller.targets.values()} == {first, unopened}
    assert controller.panel.files.topLevelItemCount() == 2
    item = controller.panel.files.topLevelItem(1)
    rectangle = controller.panel.files.visualItemRect(item)
    qtbot.mouseClick(controller.panel.files.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
    qtbot.waitUntil(lambda: window.tabs.count() == 2 and window.current_document().ready, timeout=10000)
    opened = window.current_document()
    qtbot.waitUntil(lambda: opened.focused_page == 1 and settled(opened), timeout=15000)
    assert opened.source_path == unopened
    assert opened.page_cards[1].preview._active_search_rects
    controller._activate_item(controller.panel.paragraphs.topLevelItem(0), 1)
    assert window.tabs.count() == 2 and window.current_document() is opened
    window.close_tab(window.tabs.indexOf(opened))
    assert controller.panel.files.topLevelItemCount() == 2
    controller._activate_item(controller.panel.paragraphs.topLevelItem(0))
    qtbot.waitUntil(lambda: window.tabs.count() == 2 and window.current_document().ready, timeout=10000)
    assert window.current_document().source_path == unopened


def test_folder_search_reports_unreadable_files_and_uses_open_password(qtbot, tmp_path):
    first, locked = tmp_path / 'a.pdf', tmp_path / 'locked.pdf'
    search_pdf(first, [[(40, 300, 'target first')]])
    search_pdf(locked, [[(40, 300, 'target secret')]])
    writer = PdfWriter(clone_from=locked)
    writer.encrypt('secret', algorithm='AES-256')
    writer.write(locked)
    (tmp_path / 'broken.pdf').write_bytes(b'not a PDF')
    window, _doc = load_window(qtbot, first)
    controller = window.search_controller
    controller.open()
    controller.panel.scope.setCurrentIndex(3)
    controller.panel.query.setText('target')
    controller.start()
    wait_search(qtbot, controller)
    assert len(controller.failures) == 2 and controller.panel.files.topLevelItemCount() == 1
    assert 'locked.pdf' in controller.panel.status.toolTip()
    doc = window._new_document(locked)
    doc.password = 'secret'
    doc.loaded(1)
    controller.start()
    wait_search(qtbot, controller)
    assert len(controller.failures) == 1 and controller.panel.files.topLevelItemCount() == 2
    assert {target.source_path.name for key, target in controller.targets.items() if key in controller.failures} == {'broken.pdf'}


def test_stopped_search_does_not_jump_after_a_late_open(qtbot, tmp_path, monkeypatch):
    first, second = tmp_path / 'a.pdf', tmp_path / 'b.pdf'
    for source in (first, second):
        search_pdf(source, [[(40, 300, 'target')]])
    window, _doc = load_window(qtbot, first)
    controller = window.search_controller
    controller.panel.scope.setCurrentIndex(3)
    controller.panel.query.setText('target')
    controller.start()
    wait_search(qtbot, controller)
    monkeypatch.setattr(window, 'load_pdf', lambda path: window._new_document(Path(path)))
    controller.panel.files.setCurrentItem(controller.panel.files.topLevelItem(1))
    pending_doc = window.current_document()
    assert not pending_doc.ready and controller.pending_activation is not None
    controller.close()
    pending_doc.loaded(1)
    controller.document_loaded(pending_doc)
    assert controller.pending_activation is None
    assert not pending_doc.pages.highlights


def test_changed_folder_result_requires_a_new_search(qtbot, tmp_path):
    first, second = tmp_path / 'a.pdf', tmp_path / 'b.pdf'
    for source in (first, second):
        search_pdf(source, [[(40, 300, 'target')]])
    window, _doc = load_window(qtbot, first)
    controller = window.search_controller
    controller.panel.scope.setCurrentIndex(3)
    controller.panel.query.setText('target')
    controller.start()
    wait_search(qtbot, controller)
    second.write_bytes(b'changed after search')
    controller.panel.files.setCurrentItem(controller.panel.files.topLevelItem(1))
    assert window.tabs.count() == 1
    assert '重新搜尋' in controller.panel.status.text()
