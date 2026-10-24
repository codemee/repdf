"""Save the active document independently of selected-page exports."""
from pathlib import Path
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox
from repdf.renderer import RenderService, start_render_backend
from repdf.strings import tr, localize_text
from repdf.workers import SavePdfTask


class SaveController(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.task = None
        self.doc = None
        self.after_save = None

    def choose(self, save_as=False, on_saved=None):
        w = self.owner
        w.annotation_editor.finish_text(True)
        doc = w.current_document()
        if (doc is None or not doc.ready or w._export_running or w.print_controller.busy
                or (not save_as and not doc.modified)):
            return
        destination, overwrite = doc.source_path, False
        dialog_parent = w._fullscreen_preview or w
        if save_as:
            filename, _ = QFileDialog.getSaveFileName(
                dialog_parent, tr('另存新檔'), str(destination), tr('PDF 檔案 (*.pdf)'), '',
                QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.DontConfirmOverwrite)
            if not filename:
                return
            destination = Path(filename).with_suffix('.pdf').resolve()
            if any(other is not doc and other.source_path == destination for other in w.documents.values()):
                QMessageBox.warning(dialog_parent, tr('無法儲存'), tr('目的檔案已在其他標籤開啟，請選擇其他檔名。'))
                return
            if destination.exists():
                if QMessageBox.question(dialog_parent, tr('確認覆蓋'), tr('檔案已存在，是否覆蓋？\n{p0}', p0=destination),
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                        QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    return
                overwrite = True
        self.start(doc, destination, overwrite=overwrite, on_saved=on_saved)

    def start(self, doc, destination, *, overwrite=False, on_saved=None):
        w = self.owner
        if w._export_running or w.print_controller.busy:
            return
        self.doc = doc
        self.after_save = on_saved
        self.order = tuple(doc.page_order)
        self.page = self.order.index(doc.preview_page_index())
        self.selected = {i for i, page in enumerate(self.order) if page in doc.selected_pages}
        self.included = doc.include_checkbox.isChecked()
        w._set_export_running(True)
        w.toolbar.setEnabled(False)
        w.tabs.setEnabled(False)
        if w._fullscreen_preview is not None:
            w._fullscreen_preview.close()
        w.setEnabled(False)
        w.navigation.shutdown()
        w.navigation.requests.clear()
        w.navigation.latest_jump = None
        w.search_controller.stop()
        for other in w.documents.values():
            other.render_timer.stop()
            other.fit_timer.stop()
            other.pages.scroll_timer.stop()
        # Windows PDFium handles must close before replacing a source file.
        w.render_service.message.disconnect(w._handle_render_message)
        w.render_service.close(terminate_tree=True)
        w._render_documents.clear()
        w._text_requests.clear()
        w._image_requests.clear()
        w._ocr_generations.clear()
        w.statusBar().showMessage(tr('正在儲存 PDF…'))
        self.task = SavePdfTask(doc.source_path, destination, self.order, doc.password, overwrite, tuple(doc.annotation_store.changes()))
        self.task.signals.completed.connect(self.completed)
        self.task.signals.failed.connect(self.failed)
        w.thread_pool.start(self.task)

    def resume(self):
        w = self.owner
        old = w.render_service
        w.render_service = RenderService(start_render_backend(), w)
        w.render_service.message.connect(w._handle_render_message, Qt.ConnectionType.QueuedConnection)
        old.deleteLater()
        w.setEnabled(True)
        w.toolbar.setEnabled(True)
        w.tabs.setEnabled(True)
        w._set_export_running(False)
        for doc in w.documents.values():
            doc.pages.batch = []
            doc.render_generation = -1
            doc.render_timer.start()
            if doc.fit_mode:
                doc.fit_timer.start()

    def completed(self, _session, destination, count):
        w, old_doc = self.owner, self.doc
        if w._closing:
            return
        self.resume()
        index = w.tabs.indexOf(old_doc)
        password, zoom, fit = old_doc.password, old_doc.zoom, old_doc.fit_mode
        w.close_tab(index, force=True)
        doc = w._new_document(destination)
        doc.password, doc.zoom, doc.fit_mode = password, zoom, fit
        doc.fit_page_index = self.page
        doc.selected_pages = self.selected
        doc.loaded(count)
        doc.include_checkbox.setChecked(self.included)
        w.tabs.tabBar().moveTab(w.tabs.indexOf(doc), index)
        doc.jump_to_page(self.page)
        w._sync_controls()
        w.navigation.show_document()
        w.statusBar().showMessage(tr('已儲存 PDF：{p0}', p0=destination))
        self.task = None
        self.doc = None
        callback, self.after_save = self.after_save, None
        if callback:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: callback(doc))

    def failed(self, _session, message):
        if self.owner._closing:
            return
        self.resume()
        self.task = None
        self.doc = None
        self.after_save = None
        self.owner._discard_on_close.clear()
        QMessageBox.critical(self.owner, tr('儲存失敗'), localize_text(message))
