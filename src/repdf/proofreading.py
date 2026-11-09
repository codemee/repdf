"""Explicit two-tab fullscreen comparison and atomic page synchronization."""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QMenu, QToolTip, QWidget

from repdf.strings import tr
from repdf.message_dialogs import proofreading_range_message


class ProofreadingController(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.busy = False
        self.activating = False
        self.pair_ids = None
        owner.sync_views_action.toggled.connect(self.toggle)
        QApplication.instance().installEventFilter(self)

    def selected(self):
        return [doc for doc in self.owner.ordered_documents() if doc.include_checkbox.isChecked()]

    def viewer(self):
        viewer = self.owner._fullscreen_preview
        return viewer if viewer is not None and hasattr(viewer, 'views') else None

    def active_sync(self):
        return self.viewer() is not None and self.owner.sync_views_action.isChecked()

    def refresh(self):
        selected = self.selected()
        ids = tuple(doc.document_id for doc in selected)
        ready = len(selected) == 2 and all(doc.ready for doc in selected)
        if not ready or self.pair_ids != ids:
            self.owner.sync_views_action.setChecked(False)
        self.pair_ids = ids
        action = self.owner.sync_views_action
        action.setEnabled(ready and not self.owner._export_running)
        action.setText(tr('同步校對'))
        action.setToolTip(tr('同步校對：勾選兩個標籤後可啟用，只同步跳頁與裁切'))
        too_many = len(selected) > 2
        current = selected[0] if selected else self.owner.current_document()
        available = bool(current is not None and current.ready and (current.page_sizes or ready)
                         and not self.owner._export_running)
        available = available and not too_many and (len(selected) != 2 or ready)
        self.owner.fullscreen_action.setEnabled(available)
        compare = self.viewer() is not None or len(selected) == 2
        hint = tr('校對模式只能比對兩份文件，請最多勾選兩個標籤。') if too_many else (
            tr('全螢幕校對：左右比對兩份文件') if compare else self.owner.fullscreen_action.toolTip())
        self.owner.fullscreen_action.setToolTip(hint)
        self.owner.fullscreen_menu_button.setEnabled(available)
        self.owner.fullscreen_menu_button.setToolTip(hint)
        for button in (self.owner.toolbar.widgetForAction(self.owner.fullscreen_action),
                       self.owner.fullscreen_menu_button):
            button.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        for mode_action in (self.owner.single_action, self.owner.spread_action, self.owner.cover_action):
            mode_action.setEnabled(available)

    def toggle(self, checked):
        if not checked:
            return
        selected = self.selected()
        if len(selected) != 2:
            self.owner.sync_views_action.setChecked(False)
            return
        if self.viewer() is None:
            if self.owner._fullscreen_preview is not None:
                self.owner._fullscreen_preview.close()
            if self.owner.current_document() not in selected:
                self.owner.activate_document(selected[0])
            self.owner._show_fullscreen_preview()
        viewer = self.viewer()
        if viewer is None:
            self.owner.sync_views_action.setChecked(False)
            return
        page = viewer.page_index
        if self.allow_page(viewer.document, page):
            self.page_changed(viewer.document, page)
        self.owner._toggle_trim_view(viewer.document.trim_view)

    def allow_page(self, doc, page):
        viewer = self.viewer()
        if self.busy or not self.active_sync() or doc.document_id not in viewer.views:
            return True
        for view in viewer.views.values():
            if not 0 <= page < view.document.page_count:
                message = proofreading_range_message(viewer, page + 1, view.document.source_path.name,
                                                     view.document.page_count)
                message.exec()
                return False
        return True

    def page_changed(self, doc, page):
        if self.busy or not self.active_sync():
            return
        self.busy = True
        try:
            for view in self.viewer().views.values():
                if view.document is not doc and view.page_index != page:
                    view.show_page(page)
        finally:
            self.busy = False

    def eventFilter(self, watched, event):
        if self.owner._closing or not isinstance(watched, QWidget):
            return False
        if event.type() == QEvent.Type.ToolTip and len(self.selected()) > 2:
            if isinstance(watched, QMenu) and watched.actionAt(event.pos()) is self.owner.fullscreen_action:
                QToolTip.showText(event.globalPos(), self.owner.fullscreen_action.toolTip(), watched)
                return True
            for button in (self.owner.toolbar.widgetForAction(self.owner.fullscreen_action),
                           self.owner.fullscreen_menu_button):
                if button.isVisible() and button.rect().contains(button.mapFromGlobal(event.globalPos())):
                    QToolTip.showText(event.globalPos(), self.owner.fullscreen_action.toolTip(), button)
                    return True
        viewer = self.viewer()
        if viewer is None or event.type() not in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            return False
        view = next((v for key, v in viewer.views.items()
                     if watched is viewer.frames[key] or viewer.frames[key].isAncestorOf(watched)), None)
        if view is not None and not self.activating:
            self.activating = True
            try:
                if self.owner.current_document() is not view.document:
                    self.owner.activate_document(view.document)
                viewer.mark_active()
            finally:
                self.activating = False
        if view is not None and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta:
                view._handle_key(Qt.Key.Key_PageUp if delta > 0 else Qt.Key.Key_PageDown)
                return True
        return False
