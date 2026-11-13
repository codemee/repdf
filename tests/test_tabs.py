from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QToolButton, QCheckBox, QTabBar

from repdf.tabs import DocumentTabs


def test_pending_alignment_is_cancelled_when_tabs_are_deleted(qtbot, qapp):
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid
    tabs = DocumentTabs()
    tabs._layout_timer.start(0)
    tabs.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(tabs)
    qapp.processEvents()


def test_native_scroll_arrows_and_document_dropdown(qtbot):
    tabs = DocumentTabs()
    qtbot.addWidget(tabs)
    tabs.setMovable(True)
    tabs.setDocumentMode(True)
    tabs.setStyleSheet('QTabWidget::pane { border: none; } '
                      'QTabBar::tab { padding: 5px 8px; border-bottom: 2px solid transparent; } '
                      'QToolButton { padding: 4px; border: 1px solid transparent; }')
    tabs.resize(360, 240)
    documents = []
    for index in range(12):
        doc = QWidget()
        doc.source_path = Path(f'/folder-{index}/Full document name {index}.pdf')
        doc.document_id = index
        doc.modified = index == 2
        tabs.addTab(doc, f'Document {index}')
        documents.append(doc)
    tabs.show()
    qtbot.waitExposed(tabs)
    native_arrows = [button for button in tabs.tabBar().findChildren(QToolButton)
              if button.objectName() in ('ScrollLeftButton', 'ScrollRightButton')]
    assert len(native_arrows) == 2
    assert all(button.size().isEmpty() for button in native_arrows)
    arrows = [tabs.scroll_left_button, tabs.scroll_right_button]
    assert all(button.isVisible() and button.autoRaise() for button in arrows)
    assert tabs.tab_list_button.isVisible()
    for width in (360, 600, 280):
        tabs.resize(width, 240)
        qtbot.waitUntil(lambda: tabs.tab_list_button.y() == tabs.tabBar().y()
                       and tabs.tab_list_button.height() == tabs.tabBar().height())
        qtbot.wait(10)
        tabs.grab()
        assert tabs.tab_list_button.geometry().bottom() == tabs.tabBar().geometry().bottom()
        assert tabs.tab_list_button.geometry().right() == tabs.width() - 1
        assert tabs.tabBar().geometry().right() < tabs.tab_list_button.x()
        assert tabs.scroll_left_button.x() == 0
        assert tabs.tabBar().x() >= tabs.scroll_left_button.geometry().right() + 1
        assert tabs.scroll_right_button.x() > tabs.tabBar().geometry().right()
        assert tabs.scroll_right_button.geometry().right() < tabs.tab_list_button.x()
        assert all(button.arrowType() == Qt.ArrowType.NoArrow and not button.icon().isNull()
                   for button in arrows + [tabs.tab_list_button])
    before = tabs.tabBar().tabRect(0).x()
    tabs.scroll_right_button.click()
    qtbot.waitUntil(lambda: tabs.tabBar().tabRect(0).x() < before)
    qtbot.waitUntil(tabs.scroll_left_button.isEnabled)
    tabs.scroll_left_button.click()
    qtbot.waitUntil(lambda: tabs.tabBar().tabRect(0).x() == before)
    tabs.tabBar().moveTab(2, 0)
    tabs.populate_tab_list()
    actions = tabs.tab_list_menu.actions()
    assert actions[0].text() == 'Full document name 2.pdf *'
    assert actions[0].toolTip() == str(documents[2].source_path)
    actions[0].trigger()
    assert tabs.currentWidget() is documents[2]
    tabs.populate_tab_list()
    assert tabs.tab_list_menu.actions()[0].isChecked()
    stale = tabs.tab_list_menu.actions()[1]
    removed = tabs.widget(1)
    tabs.removeTab(1)
    removed.deleteLater()
    qtbot.wait(1)
    stale.trigger()
    assert tabs.currentWidget() is documents[2]


def test_filename_sort_is_natural_stable_and_preserves_documents(qtbot):
    tabs = DocumentTabs()
    qtbot.addWidget(tabs)
    tabs.setMovable(True)
    documents = []
    for index, name in enumerate(('CH10.pdf', 'CH2.pdf', 'ch1.pdf', 'CH02.pdf', 'ch2.pdf')):
        doc = QWidget()
        doc.source_path = Path(f'/folder-{index}') / name
        doc.document_id, doc.modified = index, index == 2
        doc.checkbox = QCheckBox()
        doc.checkbox.setChecked(index == 1)
        doc.close_button = QToolButton()
        tabs.addTab(doc, name)
        tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.LeftSide, doc.checkbox)
        tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, doc.close_button)
        documents.append(doc)
    current = documents[0]
    tabs.setCurrentWidget(current)
    tabs.populate_tab_list()
    actions = tabs.tab_list_menu.actions()
    assert actions[-3].isSeparator()
    assert all(action.isEnabled() for action in actions[-2:])
    assert actions[-2].text() == '依檔名升冪排序'
    changes = []
    tabs.currentChanged.connect(changes.append)
    actions[-2].trigger()
    expected = [documents[i] for i in (2, 1, 3, 4, 0)]
    assert [tabs.widget(i) for i in range(tabs.count())] == expected
    assert tabs.currentWidget() is current and not changes
    for index in range(tabs.count()):
        doc = tabs.widget(index)
        assert tabs.tabBar().tabButton(index, QTabBar.ButtonPosition.LeftSide) is doc.checkbox
        assert tabs.tabBar().tabButton(index, QTabBar.ButtonPosition.RightSide) is doc.close_button
        assert doc.checkbox.isChecked() == (doc is documents[1])
    tabs.populate_tab_list()
    assert tabs.tab_list_menu.actions()[0].text() == 'ch1.pdf *'
    tabs.tab_list_menu.actions()[-1].trigger()
    # Equal natural keys retain their relative order, even in descending mode.
    assert [tabs.widget(i) for i in range(tabs.count())] == [documents[i] for i in (0, 1, 3, 4, 2)]
    assert tabs.currentWidget() is current
    tabs.tabBar().moveTab(0, 4)
    assert tabs.widget(4) is current


def test_sort_disabled_for_empty_single_or_locked_tabs(qtbot):
    tabs = DocumentTabs()
    qtbot.addWidget(tabs)
    tabs.setMovable(True)
    for count in range(3):
        tabs.populate_tab_list()
        assert all(action.isEnabled() == (count > 1) for action in tabs.tab_list_menu.actions()[-2:])
        doc = QWidget()
        doc.source_path = Path(f'CH{2-count}.pdf')
        doc.document_id, doc.modified = count, False
        tabs.addTab(doc, doc.source_path.name)
    before = [tabs.widget(i) for i in range(tabs.count())]
    tabs.setMovable(False)
    tabs.populate_tab_list()
    assert not any(action.isEnabled() for action in tabs.tab_list_menu.actions()[-2:])
    tabs.sort_tabs()
    assert [tabs.widget(i) for i in range(tabs.count())] == before


def test_sort_is_pane_local_and_workspace_restores_sorted_order(qtbot, tmp_path, monkeypatch):
    from pypdf import PdfWriter
    from repdf.app import MainWindow, DocumentView
    from test_gui import ready_document
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    paths = [tmp_path / name for name in ('CH10.pdf', 'CH2.pdf', 'CH1.pdf', 'Other.pdf')]
    for path in paths:
        writer = PdfWriter()
        writer.add_blank_page(300, 400)
        writer.write(path)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    docs = [ready_document(window, path, 1) for path in paths]
    left = window.tabs
    docs[1].include_checkbox.setChecked(True)
    assert window.workspace.transfer(docs[3].document_id, left, 'right')
    right = window.workspace.pane_for(docs[3])
    local_current = left.currentWidget()
    left.sort_tabs()
    assert [left.widget(i).source_path for i in range(left.count())] == [paths[i] for i in (2, 1, 0)]
    assert left.currentWidget() is local_current
    assert window.workspace.active is right and window.current_document() is docs[3]
    assert right.count() == 1 and right.currentWidget() is docs[3]
    assert docs[1].include_checkbox.isChecked()
    assert left.tabBar().tabButton(left.indexOf(docs[1]), QTabBar.ButtonPosition.LeftSide) is docs[1].include_checkbox
    window.close()
    restored = MainWindow()
    qtbot.addWidget(restored)
    restored.show()
    qtbot.waitUntil(lambda: len(restored.documents) == 4 and
                   all(doc.ready for doc in restored.documents.values()), timeout=15000)
    restored_left = next(pane for pane in restored.workspace.panes if pane.count() == 3)
    assert [restored_left.widget(i).source_path for i in range(3)] == [paths[i] for i in (2, 1, 0)]
    assert restored_left.currentWidget().source_path == local_current.source_path
    assert restored.current_document().source_path == paths[3]
