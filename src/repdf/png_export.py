"""Page PNG rendering in a cancellable PDFium subprocess."""

import os
import tempfile
from math import ceil
from pathlib import Path

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QProgressDialog

from repdf.renderer import RenderService, start_render_backend
from repdf.strings import tr


def png_output_paths(destination, count):
    if count < 1:
        raise ValueError(tr('請至少選取一頁。'))
    path = Path(destination).with_suffix('.png')
    if count == 1:
        return [path]
    digits = max(2, len(str(count)))
    return [path.with_name(f'{path.stem}_{index:0{digits}d}.png') for index in range(1, count + 1)]


def render_png_pages(request, documents, emit):
    items = request['documents']
    count = sum(len(item['pages']) for item in items)
    outputs = png_output_paths(Path(request['destination']).absolute(), count)
    protected = {Path(item['source']).resolve() for item in items}
    protected.update(Path(path).resolve() for path in request.get('protected_sources', ()))
    if protected.intersection(path.resolve() for path in outputs):
        raise ValueError(tr('輸出檔案不可覆蓋來源 PDF。'))
    if not request.get('overwrite') and any(path.exists() for path in outputs):
        raise FileExistsError(tr('部分圖檔已存在，請確認覆蓋或更換檔名。'))
    staging = Path(request['staging_dir'])
    position = 0
    try:
        for item in items:
            document = documents.get(item['source'], item.get('password'), item.get('annotation_changes', ()))
            for index in item['pages']:
                if not 0 <= index < len(document):
                    raise IndexError(tr('選取的頁碼超出來源 PDF 範圍：{p0}', p0=item['source']))
                page = document[index]
                try:
                    width, height = page.get_size()
                    scale = min(300 / 72, (30_000_000 / (width * height)) ** .5)
                    while ceil(width * scale) * ceil(height * scale) > 30_000_000:
                        scale *= .999
                    bitmap = page.render(scale=scale, draw_annots=True)
                    try:
                        image = bitmap.to_pil().convert('RGB')
                        with (staging / outputs[position].name).open('wb') as stream:
                            image.save(stream, 'PNG', dpi=(scale * 72, scale * 72))
                            stream.flush()
                            os.fsync(stream.fileno())
                        image.close()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                position += 1
                emit({'type': 'png_progress', 'generation': request['generation'],
                      'count': position, 'total': count})
    finally:
        for item in items:
            documents.release(item['source'])


def publish_png_pages(staging, outputs, overwrite=False):
    published = 0
    try:
        for output in outputs:
            pending = Path(staging) / output.name
            if overwrite:
                os.replace(pending, output)
            elif os.name == 'nt':
                os.rename(pending, output)
            else:
                os.link(pending, output)
            published += 1
    except OSError as exc:
        raise OSError(tr('PNG 輸出失敗；已完成 {count} / {total} 個檔案。\n{message}',
                        count=published, total=len(outputs), message=str(exc))) from exc


class PngExportController(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.service = None
        self.staging = None
        self.progress = None
        self.outputs = []
        self.session = 0

    def start(self, selections, destination, session, overwrite):
        self.session = session
        self.destination = destination
        self.overwrite = overwrite
        self.outputs = png_output_paths(destination, sum(len(item.pages) for item in selections))
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.staging = tempfile.TemporaryDirectory(prefix='.repdf-png-', dir=destination.parent)
            self.progress = QProgressDialog(tr('正在輸出 PNG…'), tr('取消'), 0, len(self.outputs),
                                            self.owner._fullscreen_preview or self.owner)
            self.progress.setWindowTitle(tr('輸出 PNG'))
            self.progress.setAutoClose(False)
            self.progress.setAutoReset(False)
            self.progress.setMinimumDuration(500)
            self.progress.canceled.connect(self.cancel)
            self.progress.setValue(0)
            self.service = RenderService(start_render_backend(), self)
            self.service.message.connect(self.receive, Qt.ConnectionType.QueuedConnection)
            self.service.request_search({'type': 'export_png', 'generation': session, 'document_id': session,
                'destination': str(destination), 'staging_dir': self.staging.name, 'overwrite': overwrite,
                'protected_sources': [str(doc.source_path) for doc in self.owner.documents.values()],
                'documents': [{'source': str(item.source), 'pages': list(item.pages),
                               'password': item.password, 'annotation_changes': item.annotation_changes}
                              for item in selections]})
        except Exception as exc:
            self._cleanup()
            self.owner._export_failed(session, str(exc))

    def _end_service(self):
        if self.service is not None:
            service, self.service = self.service, None
            service.message.disconnect(self.receive)
            service.close(terminate_tree=True)
            service.deleteLater()

    def _cleanup(self):
        self._end_service()
        if self.progress is not None:
            self.progress.blockSignals(True)
            self.progress.close()
            self.progress.deleteLater()
            self.progress = None
        if self.staging is not None:
            self.staging.cleanup()
            self.staging = None
        self.outputs = []

    def cancel(self):
        if self.service is None and self.progress is None:
            return
        self._cleanup()
        self.owner._set_export_running(False)
        self.owner.statusBar().showMessage(tr('已取消 PNG 輸出'))

    def receive(self, payload):
        if self.service is None or payload.get('generation') != self.session:
            return
        kind = payload.get('type')
        if kind == 'png_progress':
            self.progress.setValue(payload['count'])
            self.progress.setLabelText(tr('正在輸出 PNG：{count} / {total} 頁', count=payload['count'], total=payload['total']))
        elif kind == 'done':
            count = len(self.outputs)
            self._end_service()
            try:
                publish_png_pages(self.staging.name, self.outputs, self.overwrite)
            except Exception as exc:
                self._cleanup()
                self.owner._export_failed(self.session, str(exc))
                return
            self._cleanup()
            self.owner._export_completed(self.session, self.destination, count)
        elif kind == 'error':
            self._cleanup()
            self.owner._export_failed(self.session, str(payload.get('message', '')))
