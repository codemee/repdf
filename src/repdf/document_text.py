"""Background extraction and clipboard selection of a whole PDF's text layer."""

from contextlib import closing

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit, QWidget

from repdf.renderer import RenderService, start_render_backend
from repdf.strings import tr


def extract_document_text(request, emit):
    import pypdfium2 as pdfium
    from repdf.search import normalized_box

    with closing(pdfium.PdfDocument(request['source'], password=request.get('password'))) as document:
        pages = request['pages']
        for position, index in enumerate(pages, 1):
            with closing(document[index]) as page, closing(page.get_textpage()) as textpage:
                text = textpage.get_text_range().replace('\r\n', '\n').replace('\r', '\n')
                first, last = 0, textpage.count_chars() - 1
                endpoints = request.get('endpoints', {})
                def nearest(position):
                    candidates = []
                    for char in range(textpage.count_chars()):
                        box = normalized_box(page, textpage.get_charbox(char))
                        if box:
                            candidates.append(((max(box[0] - position[0], 0, position[0] - box[2]) ** 2
                                                + max(box[1] - position[1], 0, position[1] - box[3]) ** 2), char))
                    return min(candidates)[1] if candidates else 0
                if position == 1 and 'start' in endpoints:
                    first = nearest(endpoints['start'])
                if position == len(pages) and 'end' in endpoints:
                    last = nearest(endpoints['end'])
                if textpage.count_chars():
                    first, last = sorted((first, last))
                else:
                    first, last = 0, -1
                text = textpage.get_text_range(first, last - first + 1).replace('\r\n', '\n').replace('\r', '\n') if last >= first else ''
                rects = ([normalized_box(page, textpage.get_charbox(i)) for i in range(first, last + 1)]
                         if endpoints else [normalized_box(page, textpage.get_rect(i)) for i in range(textpage.count_rects())])
            emit({'type': 'document_text_page', 'generation': request['generation'],
                  'page': index, 'position': position, 'total': len(pages),
                  'text': text, 'rects': [rect for rect in rects if rect]})


class DocumentTextCopy(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.service = None
        self.generation = 0
        self.document_id = None
        self.order = []
        self.texts = {}
        self.rects = {}
        self.copy_result = True
        from repdf.drag_selection import DragTextSelection
        self.drag = DragTextSelection(self)

    def handle_event(self, watched, event, window):
        if self.drag.handle_event(watched, event, window):
            return True
        if (self.owner._closing or not isinstance(watched, QWidget) or watched.window() is not window
                or isinstance(watched, (QLineEdit, QTextEdit, QPlainTextEdit))
                or not self.owner.copy_text_action.isChecked()
                or event.type() not in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
                or not event.matches(QKeySequence.StandardKey.SelectAll)):
            return False
        doc = self.owner.current_document()
        if doc is None or not doc.ready or self.owner._export_running:
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
        elif not event.isAutoRepeat():
            self.start(doc)
        return True

    def _end_service(self):
        if self.service is not None:
            service, self.service = self.service, None
            service.message.disconnect(self.receive)
            service.close(terminate_tree=True)
            service.deleteLater()

    def cancel(self):
        self.generation += 1
        self._end_service()
        doc = self.owner.documents.get(self.document_id)
        if doc is not None:
            for card in doc.page_cards:
                card.preview.set_text_highlights([])
            viewer = self.owner._fullscreen_preview
            if viewer is not None and viewer.document is doc:
                for label in viewer.labels.values():
                    label.set_text_highlights([])
        self.document_id = None
        self.texts.clear()
        self.rects.clear()

    def start(self, doc):
        self.cancel()
        self.document_id = doc.document_id
        self.order = list(doc.page_order)
        self.copy_result = True
        # Invalidate an earlier drag selection so it cannot overwrite this copy.
        self.owner._text_requests.clear()
        try:
            self.service = RenderService(start_render_backend(), self)
            self.service.message.connect(self.receive, Qt.ConnectionType.QueuedConnection)
            self.service.request_search({'type': 'copy_document', 'generation': self.generation,
                'document_id': doc.document_id, 'source': str(doc.source_path),
                'password': doc.password, 'pages': self.order})
            self.owner.statusBar().showMessage(tr('正在擷取整份 PDF 的文字…'))
        except Exception as exc:
            self.cancel()
            self.owner.statusBar().showMessage(tr('全文複製失敗：{message}', message=str(exc)))

    def apply_label(self, label, doc, page):
        if self.document_id == doc.document_id and page in self.rects:
            label.set_text_highlights(self.rects[page])

    def select_range(self, doc, start, end, *, copy=False):
        self.generation += 1
        self.document_id = doc.document_id
        self.order = list(doc.page_order)
        self.copy_result = copy
        a, b = self.order.index(start[0]), self.order.index(end[0])
        if a > b:
            a, b, start, end = b, a, end, start
        self.texts.clear()
        self.rects.clear()
        if self.service is None:
            self.service = RenderService(start_render_backend(), self)
            self.service.message.connect(self.receive, Qt.ConnectionType.QueuedConnection)
        self.service.request_search({'type': 'copy_document', 'generation': self.generation,
            'document_id': doc.document_id,
            'source': str(doc.source_path), 'password': doc.password, 'pages': self.order[a:b + 1],
            'endpoints': {'start': start[1], 'end': end[1]}})

    def receive(self, payload):
        if (self.owner._closing or not isinstance(payload, dict)
                or payload.get('generation') != self.generation):
            return
        doc = self.owner.documents.get(self.document_id)
        if (doc is None or self.owner.current_document() is not doc
                or not self.owner.copy_text_action.isChecked() or doc.page_order != self.order):
            self.cancel()
            return
        kind = payload.get('type')
        if kind == 'document_text_page':
            self.texts[payload['page']] = payload['text']
            self.rects[payload['page']] = payload['rects']
            self.owner.statusBar().showMessage(tr('擷取全文：第 {page} / {total} 頁', page=payload['position'], total=payload['total']))
        elif kind == 'done':
            if self.copy_result:
                self._end_service()
            text = '\n\n'.join(self.texts[page] for page in self.order if self.texts.get(page, '').strip())
            self.texts.clear()
            if text:
                if self.copy_result:
                    QApplication.clipboard().setText(text)
                for card in doc.page_cards:
                    card.preview.set_text_highlights([])
                    self.apply_label(card.preview, doc, card.page_index)
                viewer = self.owner._fullscreen_preview
                if viewer is not None and viewer.document is doc:
                    for page, label in viewer.labels.items():
                        label.set_text_highlights([])
                        self.apply_label(label, doc, page)
                if self.copy_result:
                    self.owner.statusBar().showMessage(tr('已複製整份 PDF 文字（{count} 字元）', count=len(text)))
            else:
                self.owner.statusBar().showMessage(tr('此 PDF 沒有可複製的文字層'))
        elif kind == 'error':
            self.cancel()
            self.owner.statusBar().showMessage(tr('全文複製失敗：{message}', message=payload.get('message', '')))
