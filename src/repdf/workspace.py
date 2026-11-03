"""Split document panes, tab transfer, and persistent workspace geometry."""
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QDrag, QPainter, QPalette, QPen
from PySide6.QtWidgets import QSplitter, QApplication, QTabBar, QWidget, QRubberBand, QFrame, QVBoxLayout

from repdf.tabs import DocumentTabs

TAB_MIME = 'application/x-repdf-document-tab'


class PaneTabs(DocumentTabs):
    def __init__(self, workspace):
        super().__init__()
        self.setObjectName('documentPane')
        self.workspace = workspace
        self.setAcceptDrops(True)
        self.tabBar().setAcceptDrops(True)
        self.tabBar().installEventFilter(workspace)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME):
            self.drop_document(event, event.position().toPoint())
        else:
            super().dropEvent(event)

    def drop_document(self, event, position):
        try:
            document_id = int(bytes(event.mimeData().data(TAB_MIME)))
        except ValueError:
            event.ignore()
            return
        edge = self.workspace.drop_edge(self, position)
        if self.workspace.transfer(document_id, self, edge):
            event.acceptProposedAction()
        else:
            event.ignore()


class PaneFrame(QFrame):
    def __init__(self, pane):
        super().__init__()
        self.setObjectName('documentPaneFrame')
        self.pane = pane
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(pane)
        self.separator = QFrame(self)
        self.separator.setObjectName('paneTabSeparator')
        self.separator.setFixedHeight(1)
        self.separator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        pane.tabBar().installEventFilter(self)
        self.separator.raise_()

    def _align_separator(self):
        y = self.pane.tabBar().mapTo(self, QPoint(0, self.pane.tabBar().height())).y()
        self.separator.setGeometry(2, y, max(0, self.width() - 4), 1)

    def eventFilter(self, watched, event):
        if watched is self.pane.tabBar() and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.LayoutRequest):
            self._align_separator()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._align_separator()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.property('activePane') is not True:
            return
        dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#a992c4' if dark else '#add6ff'), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 7, 7)


class PaneWorkspace(QObject):
    def __init__(self, owner, root):
        super().__init__(owner)
        self.owner = owner
        self.root = root
        self.panes = []
        self.active = self.create_pane()
        self._mark_active(self.active, True)
        self.root.addWidget(self.active.frame)
        self.drag_start = None
        self.drop_marker = QRubberBand(QRubberBand.Shape.Rectangle, self.active)
        self.drop_marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        QApplication.instance().installEventFilter(self)
        QApplication.instance().focusChanged.connect(self._focus_changed)

    @staticmethod
    def _mark_active(pane, active):
        frame = pane.frame
        frame.setProperty('activePane', active)
        frame.update()

    def _focus_changed(self, _previous, current):
        if self.owner._closing or not isinstance(current, QWidget):
            return
        pane = next((p for p in self.panes if current is p or current is p.frame
                     or p.frame.isAncestorOf(current)), None)
        if pane is not None:
            QTimer.singleShot(0, lambda p=pane: self._activate_focused(p))

    def _activate_focused(self, pane):
        if self.owner._closing or pane not in self.panes:
            return
        focused = QApplication.focusWidget()
        if focused is not None and (focused is pane or focused is pane.frame
                                    or pane.frame.isAncestorOf(focused)):
            self.activate(pane)

    def eventFilter(self, watched, event):
        if event.type() not in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                                QEvent.Type.MouseMove, QEvent.Type.Wheel,
                                QEvent.Type.DragEnter, QEvent.Type.DragMove,
                                QEvent.Type.DragLeave, QEvent.Type.Drop):
            return False
        if isinstance(watched, QWidget) and isinstance(watched.parentWidget(), PaneTabs) and watched is watched.parentWidget().tabBar():
            pane = watched.parentWidget()
            kind = event.type()
            if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                index = watched.tabAt(event.pos())
                self.drag_start = (pane, pane.widget(index) if index >= 0 else None, event.pos())
                self.activate(pane)
            elif kind == QEvent.Type.MouseMove and self.drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
                source, doc, start = self.drag_start
                if (source is pane and doc is not None and not watched.rect().contains(event.pos())
                        and (event.pos() - start).manhattanLength() >= QApplication.startDragDistance()):
                    self.drag_start = None
                    drag = QDrag(watched)
                    mime = QMimeData()
                    mime.setData(TAB_MIME, str(doc.document_id).encode())
                    drag.setMimeData(mime)
                    drag.exec(Qt.DropAction.MoveAction)
                    self.drop_marker.hide()
                    return True
            elif kind == QEvent.Type.MouseButtonRelease:
                self.drag_start = None
        if isinstance(watched, QWidget) and event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove,
                QEvent.Type.DragLeave, QEvent.Type.Drop):
            pane = watched if isinstance(watched, PaneTabs) else next(
                (p for p in self.panes if p is watched or p.frame is watched or p.isAncestorOf(watched)), None)
            if event.type() == QEvent.Type.DragLeave:
                self.drop_marker.hide()
            elif pane is not None and event.mimeData().hasFormat(TAB_MIME):
                position = watched.mapTo(pane, event.position().toPoint())
                if event.type() == QEvent.Type.Drop:
                    self.drop_marker.hide()
                    pane.drop_document(event, position)
                else:
                    self.show_drop_marker(pane, position)
                    event.acceptProposedAction()
                return True
        if isinstance(watched, QWidget) and event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            pane = next((p for p in self.panes if p is watched or p.frame is watched or p.isAncestorOf(watched)), None)
            if pane is not None and pane is not self.active:
                self.activate(pane)
        return False

    def show_drop_marker(self, pane, position):
        edge = self.drop_edge(pane, position)
        self.drop_marker.setParent(pane)
        width, height = pane.width(), pane.height()
        if edge == 'left':
            rect = (0, 0, width // 3, height)
        elif edge == 'right':
            rect = (width * 2 // 3, 0, width // 3, height)
        elif edge == 'bottom':
            rect = (0, height * 2 // 3, width, height // 3)
        else:
            rect = (width // 3, 0, width // 3, height)
        self.drop_marker.setGeometry(*rect)
        self.drop_marker.show()

    def create_pane(self):
        pane = PaneTabs(self)
        pane.frame = PaneFrame(pane)
        pane.frame.setProperty('activePane', False)
        pane.setDocumentMode(True)
        pane.setMovable(True)
        pane.setElideMode(Qt.TextElideMode.ElideRight)
        pane.tabBar().setExpanding(False)
        pane.tabBar().setDrawBase(False)
        pane.currentChanged.connect(lambda index, p=pane: self.changed(p, index))
        pane.tabBar().tabBarClicked.connect(lambda _index, p=pane: self.activate(p))
        pane.tabBar().tabMoved.connect(self.owner._sync_controls)
        self.panes.append(pane)
        return pane

    def activate(self, pane):
        if pane not in self.panes or pane is self.active:
            return
        if self.active in self.panes:
            self._mark_active(self.active, False)
        self.active = pane
        self._mark_active(pane, True)
        self.owner.tabs = pane
        self.owner._tab_changed(pane.currentIndex())

    def changed(self, pane, index):
        if pane is self.active:
            self.owner._tab_changed(index)
        else:
            self.activate(pane)

    def pane_for(self, document):
        return next((pane for pane in self.panes if pane.indexOf(document) >= 0), None)

    def documents(self):
        return [pane.widget(i) for pane in self.panes for i in range(pane.count())]

    @staticmethod
    def drop_edge(pane, position):
        bounds = pane.rect()
        if position.y() > bounds.height() * .75:
            return 'bottom'
        if position.x() < bounds.width() * .25:
            return 'left'
        if position.x() > bounds.width() * .75:
            return 'right'
        return 'center'

    def transfer(self, document_id, target, edge):
        document = self.owner.documents.get(document_id)
        if document is None or self.owner._export_running:
            return False
        source = self.pane_for(document)
        if source is None:
            return False
        if source is target and edge == 'center':
            return False
        if edge not in ('center', 'left', 'right', 'bottom'):
            return False
        if edge != 'center':
            target = self.split(target, edge)
        old_index = source.indexOf(document)
        # QTabBar deletes the old tab buttons after removeTab, even when they
        # have been reparented. Replace the document references first so
        # currentChanged callbacks cannot access the soon-to-be-deleted pair.
        document._create_tab_controls(checked=document.include_checkbox.isChecked())
        source.removeTab(old_index)
        index = target.addTab(document, document.source_path.stem)
        target.setTabToolTip(index, str(document.source_path))
        target.tabBar().setTabButton(index, QTabBar.ButtonPosition.LeftSide, document.include_checkbox)
        target.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, document.close_button)
        target.setCurrentIndex(index)
        self.activate(target)
        if source.count() == 0:
            self.remove_empty(source)
        self.owner.empty_label.setVisible(not self.documents())
        self.owner._sync_controls()
        return True

    def split(self, target, edge):
        pane = self.create_pane()
        orientation = Qt.Orientation.Vertical if edge == 'bottom' else Qt.Orientation.Horizontal
        parent = target.frame.parentWidget()
        index = parent.indexOf(target.frame)
        sizes = parent.sizes()
        extent = target.frame.height() if orientation == Qt.Orientation.Vertical else target.frame.width()
        nested = QSplitter(orientation)
        nested.setChildrenCollapsible(False)
        nested.addWidget(target.frame)
        parent.insertWidget(index, nested)
        if edge == 'left':
            nested.insertWidget(0, pane.frame)
        else:
            nested.addWidget(pane.frame)
        parent.setSizes(sizes)
        half = max(1, (extent - nested.handleWidth()) // 2)
        nested.setSizes([half, half])
        return pane

    def remove_empty(self, pane):
        if pane.count() or len(self.panes) == 1:
            return
        parent = pane.frame.parentWidget()
        if self.drop_marker.parentWidget() is pane:
            self.drop_marker.hide()
            self.drop_marker.setParent(self.root)
        self.panes.remove(pane)
        pane.frame.setParent(None)
        pane.frame.deleteLater()
        while parent is not self.root and parent.count() == 1:
            child = parent.widget(0)
            grand = parent.parentWidget()
            index = grand.indexOf(parent)
            sizes = grand.sizes()
            child.setParent(None)
            parent.setParent(None)
            grand.insertWidget(index, child)
            grand.setSizes(sizes)
            parent.deleteLater()
            parent = grand
        if self.active is pane:
            self.active = None
            self.activate(self.panes[0])

    def state(self):
        def serialize(node):
            if isinstance(node, PaneFrame):
                pane = node.pane
                current = pane.currentWidget()
                return {'files': [str(pane.widget(i).source_path) for i in range(pane.count())],
                        'current': str(current.source_path) if current else None}
            return {'orientation': 'v' if node.orientation() == Qt.Orientation.Vertical else 'h',
                    'sizes': node.sizes(), 'children': [serialize(node.widget(i)) for i in range(node.count())]}
        active = self.active.currentWidget()
        return {'tree': serialize(self.root), 'active': str(active.source_path) if active else None}

    def restore(self, state):
        """Create only panes that still contain existing PDF files."""
        def build(data):
            if 'files' in data:
                paths = [Path(path) for path in data['files'] if isinstance(path, str) and Path(path).is_file()]
                if not paths:
                    return None
                pane = self.panes[0] if len(self.panes) == 1 and self.panes[0].count() == 0 else self.create_pane()
                for path in paths:
                    self.active = pane
                    self.owner.tabs = pane
                    self.owner.load_pdf(path)
                current = data.get('current')
                for index in range(pane.count()):
                    if str(pane.widget(index).source_path) == current:
                        pane.setCurrentIndex(index)
                return pane.frame
            children = [built for child in data.get('children', []) if (built := build(child)) is not None]
            if not children:
                return None
            if len(children) == 1:
                return children[0]
            splitter = QSplitter(Qt.Orientation.Vertical if data.get('orientation') == 'v' else Qt.Orientation.Horizontal)
            for child in children:
                splitter.addWidget(child)
            sizes = data.get('sizes', [])
            if len(sizes) == len(children):
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda s=splitter, v=sizes: s.setSizes(v))
            return splitter
        tree = state.get('tree', {})
        first = self.root.widget(0)
        first.setParent(None)
        built = build(tree)
        if built is None:
            self.root.addWidget(first)
            return
        self.root.addWidget(built)
        for pane in list(self.panes):
            if pane.count() == 0 and pane.frame is not built:
                if self.drop_marker.parentWidget() is pane:
                    self.drop_marker.setParent(self.root)
                self.panes.remove(pane)
                pane.frame.setParent(None)
                pane.frame.deleteLater()
        self.owner.empty_label.hide()
        self.owner.pane_root.show()
        active_path = state.get('active')
        selected = next((pane for pane in self.panes if any(
            str(pane.widget(i).source_path) == active_path for i in range(pane.count()))), self.panes[0])
        for pane in self.panes:
            self._mark_active(pane, False)
        self.active = None
        self.activate(selected)
