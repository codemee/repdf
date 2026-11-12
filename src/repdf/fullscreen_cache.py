"""Bounded full-resolution cache and idle, one-page-at-a-time lookahead."""
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage


class FullscreenCache:
    MAX_BYTES = 128 * 1024 * 1024
    MAX_PAGES = 8

    def __init__(self, viewer):
        self.viewer = viewer
        self.entries = OrderedDict()
        self.context = None
        self.generation = None
        self.waiting = True
        self.scale = 0
        self.tried = set()
        self.timer = QTimer(viewer)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.prepare_next)

    @property
    def key(self):
        return ('fullscreen-prefetch', self.viewer.document.document_id)

    def signature(self):
        v = self.viewer
        return (v.width(), v.height(), v.devicePixelRatioF(), v.mode,
                v.document.trim_view, v.document.annotation_store.revision)

    def sync(self):
        signature = self.signature()
        if signature != self.context:
            self.pause()
            self.entries.clear()
            self.context = signature

    def pause(self):
        self.timer.stop()
        self.viewer.owner.render_service.cancel_pending(self.key)
        self.generation = None
        self.waiting = True
        self.tried.clear()

    def close(self):
        self.pause()
        self.entries.clear()

    def scale_for(self, pages):
        v, sizes, area = self.viewer, {}, 0
        for page in pages:
            width, height = v.document.page_sizes.get(page, (595, 842))
            area += width * height
            trim = v.document.trim_boxes.get(page) if v.document.trim_view else None
            sizes[page] = (width * (trim[2] - trim[0]), height * (trim[3] - trim[1])) if trim else (width, height)
        return min(v._fit_scale(sizes) * v.devicePixelRatioF(), (30_000_000 / max(1, area)) ** .5)

    def get(self, page, scale=0):
        self.sync()
        entry = self.entries.get(page)
        if entry is not None and entry[0] + .001 >= scale:
            self.entries.move_to_end(page)
            return entry

    def remember(self, page, scale, image, payload):
        self.sync()
        if image.isNull() or image.sizeInBytes() > self.MAX_BYTES:
            return
        existing = self.entries.get(page)
        if existing and existing[0] > scale:
            return
        metadata = {key: value for key, value in payload.items() if key != 'path'}
        self.entries[page] = (scale, image, metadata)
        self.entries.move_to_end(page)
        while (len(self.entries) > self.MAX_PAGES or
               sum(entry[1].sizeInBytes() for entry in self.entries.values()) > self.MAX_BYTES):
            self.entries.popitem(last=False)

    def restore_visible(self):
        for page in self.viewer.visible_pages:
            entry = self.get(page)
            if entry:
                self.viewer.accept_render(entry[2], image=entry[1])

    def ready(self):
        self.waiting = False
        if not self.viewer.closed:
            self.timer.start()

    def prepare_next(self):
        v = self.viewer
        if v.closed or self.waiting or v.timer.isActive() or self.generation is not None:
            return
        self.sync()
        # A changed context needs the visible page rendered first.
        if self.waiting:
            return
        for group in v.groups[v.group_index + 1:v.group_index + 3]:
            scale = self.scale_for(group)
            for page in group:
                attempt = (page, round(scale, 6))
                if attempt in self.tried or self.get(page, scale):
                    continue
                self.tried.add(attempt)
                v.owner._next_generation += 1
                self.generation = v.owner._next_generation
                self.scale = scale
                v.owner.render_service.request(v.document.source_path, scale,
                    Path(v.owner.preview_temp.name), self.generation, document_id=self.key,
                    pages=[page], password=v.document.password, background=True)
                return

    def accept(self, payload):
        if self.viewer.closed or payload.get('generation') != self.generation:
            return False
        if payload.get('type') == 'page':
            path = Path(payload['path'])
            image = QImage(str(path)).copy()
            path.unlink(missing_ok=True)
            if self.signature() == self.context:
                page = int(payload['page'])
                self.remember(page, self.scale, image, payload)
                # Metadata lets the next request use the real page dimensions.
                self.viewer.document.page_sizes[page] = (float(payload['width_points']), float(payload['height_points']))
                if payload.get('trim_rect') is not None:
                    self.viewer.document.trim_boxes[page] = payload['trim_rect']
                else:
                    self.viewer.document.trim_boxes.pop(page, None)
        elif payload.get('type') in ('done', 'error'):
            self.generation = None
            if not self.waiting:
                self.timer.start()
        return True
