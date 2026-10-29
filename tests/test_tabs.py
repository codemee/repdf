from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QToolButton

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
