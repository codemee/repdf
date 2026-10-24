"""Toolbar styles and interactive editing shared by normal/fullscreen previews."""

from copy import deepcopy
from html import escape as html_escape
import json
from uuid import uuid4

from PySide6.QtCore import QObject, QEvent, QPointF, QRectF, QSize, QSizeF, QTimer, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QFont,
    QFontMetricsF,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from repdf.annotation_data import bounds, validate
from repdf.annotation_spin import AnnotationSpinBox, AnnotationDoubleSpinBox
from repdf.annotation_geometry import (
    DRAWINGS,
    TEXT_TOOLS,
    MARKUPS,
    category,
    rect_for,
    new_drawing,
    resize,
)
from repdf.annotation_graphics import (
    transform,
    paint,
    appearance,
    moved,
    reroute,
    selection_top_center,
)
from repdf.icons import toolbar_icon
from repdf.strings import tr, localize_text

DEFAULT_MARK = {"kind": "underline", "color": "#ff0000", "width": 1.0}
DEFAULT_CALLOUT = {
    "kind": "callout",
    "color": "#ff0000",
    "width": 1.0,
    "text_color": "#0000ff",
    "size": 12,
    "background": None,
    "ending": "OpenArrow",
    "radius": 6.0,
}
DEFAULT_DRAW = {
    "kind": "rectangle",
    "color": "#e04444",
    "width": 2.0,
    "background": None,
}

KINDS = {
    "highlight": "螢光筆",
    "underline": "底線",
    "strikeout": "刪除線",
    "squiggly": "波浪線",
    "callout": "箭頭文字框",
    "note": "便利貼",
    "line": "直線",
    "arrow": "箭頭",
    "rectangle": "矩形",
    "ellipse": "橢圓",
    "ink": "自由手繪",
}


def tool_icon(kind):
    return toolbar_icon(
        "annotation_" + kind
        if kind in MARKUPS or kind == "callout"
        else "note"
        if kind == "note"
        else kind
    )


class StyleMenu(QMenu):
    def __init__(self, editor, callout):
        super().__init__(editor.owner)
        self.editor, self.group = editor, callout
        self.drawing = callout == "draw"
        self.callout = callout is True
        callout = self.callout
        host = QWidget()
        self.host = host
        layout = QFormLayout(host)
        self.form = layout
        self.style_buttons = {}
        row = QWidget()
        buttons = QHBoxLayout(row)
        buttons.setContentsMargins(0, 0, 0, 0)
        kinds = (
            ("line", "arrow", "rectangle", "ellipse", "ink")
            if self.drawing
            else ("callout", "note")
            if callout
            else ("highlight", "underline", "strikeout", "squiggly")
        )
        for kind in kinds:
            button = QToolButton()
            button.setCheckable(True)
            button.setFixedSize(34, 34)
            button.setIconSize(QSize(20, 20))
            button.setProperty("stateButton", True)
            button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            button.setToolTip(tr(KINDS[kind]))
            button.setAccessibleName(tr(KINDS[kind]))
            button.setIcon(tool_icon(kind))
            button.clicked.connect(lambda _=False, k=kind: self.change("kind", k))
            buttons.addWidget(button)
            self.style_buttons[kind] = button
        layout.addRow(
            tr("繪圖工具" if self.drawing else "文字工具" if callout else "畫線方式"),
            row,
        )
        self.line = self.colour_button("color")
        layout.addRow(tr("線條顏色"), self.line)
        self.width = AnnotationDoubleSpinBox()
        self.width.setRange(0.5, 6)
        self.width.setSingleStep(0.5)
        self.width.setSuffix(" pt")
        self.width.valueChanged.connect(lambda value: self.change("width", value))
        layout.addRow(tr("線條粗細"), self.width)
        if not callout and not self.drawing:
            self.companion_check = QCheckBox(tr("連帶加入文字註解"))
            self.companion_check.toggled.connect(
                lambda enabled: self.companion_changed(enabled=enabled)
            )
            layout.addRow(self.companion_check)
            self.companion_row = QWidget()
            companion_layout = QHBoxLayout(self.companion_row)
            companion_layout.setContentsMargins(0, 0, 0, 0)
            self.companion_buttons = {}
            for kind in ("callout", "note"):
                button = QToolButton()
                button.setCheckable(True)
                button.setProperty("stateButton", True)
                button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                button.setFixedSize(34, 34)
                button.setIconSize(QSize(20, 20))
                button.setToolTip(tr(KINDS[kind]))
                button.setAccessibleName(tr(KINDS[kind]))
                button.clicked.connect(
                    lambda _=False, k=kind: self.companion_changed(kind=k)
                )
                companion_layout.addWidget(button)
                self.companion_buttons[kind] = button
            companion_layout.addStretch(1)
            layout.addRow(tr("文字工具"), self.companion_row)
        if callout:
            self.text = self.colour_button("text_color")
            layout.addRow(tr("文字顏色"), self.text)
            self.size = AnnotationSpinBox()
            self.size.setRange(8, 72)
            self.size.setSuffix(" pt")
            self.size.valueChanged.connect(lambda value: self.change("size", value))
            layout.addRow(tr("字級"), self.size)
            self.radius = AnnotationDoubleSpinBox()
            self.radius.setRange(0, 24)
            self.radius.setSuffix(" pt")
            self.radius.valueChanged.connect(lambda value: self.change("radius", value))
            layout.addRow(tr("圓角"), self.radius)
            self.transparent = QCheckBox(tr("透明背景"))
            self.transparent.toggled.connect(self.background_changed)
            layout.addRow(self.transparent)
            self.background = self.colour_button("background")
            layout.addRow(tr("背景顏色"), self.background)
        if self.drawing:
            self.transparent = QCheckBox(tr("透明背景"))
            self.transparent.toggled.connect(self.background_changed)
            layout.addRow(self.transparent)
            self.background = self.colour_button("background")
            layout.addRow(tr("填滿顏色"), self.background)
        wrapper = QWidgetAction(self)
        wrapper.setDefaultWidget(host)
        self.wrapper = wrapper
        self.addAction(wrapper)
        self.aboutToShow.connect(self.refresh)

    def colour_button(self, key):
        button = QToolButton()
        button.setFixedSize(54, 28)

        def choose():
            style = self.editor.style(self.group)
            value = QColorDialog.getColor(
                QColor(style.get(key) or "#ffffff"), self, tr("選擇顏色")
            )
            if value.isValid():
                self.change(key, value.name())

        button.clicked.connect(choose)
        return button

    def change(self, key, value):
        self.editor.change_style(self.group, key, value)
        if key == "kind":
            action = (
                self.editor.draw_action
                if self.drawing
                else self.editor.callout_action
                if self.callout
                else self.editor.mark_action
            )
            action.setChecked(True)
        self.refresh()

    def companion_changed(self, *, enabled=None, kind=None):
        self.editor.set_mark_companion(enabled=enabled, kind=kind)
        self.editor.mark_action.setChecked(True)
        self.refresh()

    def background_changed(self, checked):
        self.change("background", None if checked else "#ffffff")

    def refresh(self):
        style = self.editor.style(self.group)
        for key, button in self.style_buttons.items():
            button.setChecked(key == style["kind"])
            button.setIcon(tool_icon(key))
        for key, button in [("color", self.line)] + (
            [("text_color", self.text), ("background", self.background)]
            if self.callout
            else [("background", self.background)]
            if self.drawing
            else []
        ):
            button.setStyleSheet(
                "QToolButton { background: "
                + (style.get(key) or "#ffffff")
                + "; border: 1px solid palette(mid); border-radius: 4px; }"
            )
            button.setAccessibleName(tr("選擇顏色"))
        self.width.blockSignals(True)
        self.width.setValue(style["width"])
        self.width.blockSignals(False)
        self.width.setEnabled(style["kind"] not in ("highlight", "note"))
        if self.callout:
            self.size.blockSignals(True)
            self.size.setValue(style.get("size", self.editor.callout_style["size"]))
            self.size.blockSignals(False)
            self.radius.blockSignals(True)
            self.radius.setValue(style.get("radius", 0))
            self.radius.blockSignals(False)
            self.transparent.blockSignals(True)
            self.transparent.setChecked(not style.get("background"))
            self.transparent.blockSignals(False)
            self.background.setEnabled(
                style["kind"] == "callout" and bool(style.get("background"))
            )
            for control in (self.text, self.size, self.radius, self.transparent):
                control.setEnabled(style["kind"] == "callout")
            for control in (
                self.width,
                self.text,
                self.size,
                self.radius,
                self.transparent,
                self.background,
            ):
                self.form.setRowVisible(control, style["kind"] == "callout")
            self.form.labelForField(self.line).setText(
                tr("便利貼顏色" if style["kind"] == "note" else "線條顏色")
            )
        if self.drawing:
            self.transparent.blockSignals(True)
            self.transparent.setChecked(not style.get("background"))
            self.transparent.blockSignals(False)
            self.transparent.setEnabled(style["kind"] in ("rectangle", "ellipse"))
            for control in (self.transparent, self.background):
                self.form.setRowVisible(
                    control, style["kind"] in ("rectangle", "ellipse")
                )
            self.background.setEnabled(
                style["kind"] in ("rectangle", "ellipse")
                and bool(style.get("background"))
            )

        if hasattr(self, "companion_check"):
            companion = self.editor.mark_companion
            self.companion_check.blockSignals(True)
            self.companion_check.setChecked(companion["enabled"])
            self.companion_check.blockSignals(False)
            self.form.setRowVisible(self.companion_row, companion["enabled"])
            for kind, button in self.companion_buttons.items():
                button.setIcon(tool_icon(kind))
                button.setChecked(kind == companion["kind"])

        # QWidgetAction/QMenu cache their size. Recompute after rows are hidden
        # or restored when switching between note/callout and drawing types.
        self.form.invalidate()
        self.form.activate()
        self.host.setMinimumSize(self.form.minimumSize())
        self.host.adjustSize()
        self.host.updateGeometry()
        # QMenu caches QWidgetAction rectangles despite the host layout change.
        # An action-list change invalidates that cache without replacing the host.
        layout_action = QAction(self)
        self.addAction(layout_action)
        self.removeAction(layout_action)
        layout_action.deleteLater()
        self.adjustSize()


class AnnotationEditor(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.selected = None
        self.pending = None
        self.drag = None
        self.anchor = None
        self.mark_preview = None
        self.mark_highlights = None
        self.mark_timer = QTimer(self)
        self.mark_timer.setSingleShot(True)
        self.mark_timer.setInterval(90)
        self.mark_timer.timeout.connect(self.preview_mark)
        self.draft = None
        self.text_edit = None
        self.dismiss_click = False
        self.edit_model = None
        self.requests = {}
        self.pending_click = None
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.open_clicked_annotation)
        self.labels = []
        self.linked_store = None

        def read(key, default):
            try:
                result = dict(default)
                result.update(json.loads(owner.settings.value(key, "{}")))
                return result
            except (ValueError, TypeError):
                return dict(default)

        self.mark_style = read("annotation/mark", DEFAULT_MARK)
        self.mark_companion = read(
            "annotation/markup_text", {"enabled": False, "kind": "callout"}
        )
        self.callout_style = read("annotation/callout", DEFAULT_CALLOUT)
        self.draw_style = read("annotation/draw", DEFAULT_DRAW)
        self.note_color = owner.settings.value("annotation/note_color", "#c69214")
        self.mark_action = QAction(tr("文字畫線"), owner)
        self.mark_action.setToolTip(
            tr("文字畫線：拖曳選取文字建立螢光筆、底線、刪除線或波浪線")
        )
        self.mark_action.setCheckable(True)
        self.callout_action = QAction(tr("文字註解"), owner)
        self.callout_action.setToolTip(
            tr("文字註解：選擇箭頭文字框或便利貼，點選頁面新增；雙擊可編輯文字")
        )
        self.callout_action.setCheckable(True)
        self.draw_action = QAction(tr("繪圖註解"), owner)
        self.draw_action.setCheckable(True)
        self.draw_action.setToolTip(
            tr("繪圖註解：拖曳建立直線、箭頭、矩形、橢圓或自由手繪")
        )
        self.draw_action.toggled.connect(
            lambda enabled: self.mode_changed(self.draw_action, enabled)
        )
        self.mark_action.toggled.connect(
            lambda enabled: self.mode_changed(self.mark_action, enabled)
        )
        self.callout_action.toggled.connect(
            lambda enabled: self.mode_changed(self.callout_action, enabled)
        )
        self.mark_menu = StyleMenu(self, False)
        self.callout_menu = StyleMenu(self, True)
        self.draw_menu = StyleMenu(self, "draw")
        toolbar = owner.annotation_toolbar
        self.mark_arrow = toolbar.add_action_menu_group(
            self.mark_action, self.mark_menu, arrow_name="annotationLineMenu"
        )
        self.callout_arrow = toolbar.add_action_menu_group(
            self.callout_action, self.callout_menu, arrow_name="annotationCalloutMenu"
        )
        self.draw_arrow = toolbar.add_action_menu_group(
            self.draw_action, self.draw_menu, arrow_name="annotationDrawingMenu"
        )
        self.draw_arrow.setToolTip(tr("繪圖註解設定"))
        self.mark_arrow.setToolTip(tr("文字畫線設定"))
        self.callout_arrow.setToolTip(tr("文字註解設定"))
        self.refresh_icons()
        QApplication.instance().installEventFilter(self)

    def mode(self):
        return (
            "mark"
            if self.mark_action.isChecked()
            else "callout"
            if self.callout_action.isChecked()
            else "draw"
            if self.draw_action.isChecked()
            else None
        )

    def mode_changed(self, active, enabled):
        if enabled:
            self.finish_text(True)
        if self.text_edit is None:
            self.draft = None
        self.click_timer.stop()
        self.pending_click = None
        self.requests.clear()
        self.mark_timer.stop()
        self.mark_preview = None
        self.mark_highlights = None
        if enabled:
            for action in (
                self.mark_action,
                self.callout_action,
                self.draw_action,
                self.owner.copy_text_action,
                self.owner.region_ocr_action,
                self.owner.extract_image_action,
            ):
                if action is not active:
                    action.blockSignals(True)
                    action.setChecked(False)
                    action.blockSignals(False)
            self.owner._sync_selection_modes()
        self.anchor = None
        self.drag = None
        self.repaint()

    def refresh_icons(self):
        self.mark_action.setIcon(toolbar_icon("annotation_" + self.mark_style["kind"]))
        self.callout_action.setIcon(tool_icon(self.callout_style["kind"]))
        self.draw_action.setIcon(tool_icon(self.draw_style["kind"]))
        for arrow in (self.mark_arrow, self.callout_arrow, self.draw_arrow):
            arrow.setIcon(toolbar_icon("chevron_down"))

    def attach(self, label, doc, page):
        label.annotation_editor = self
        label.annotation_document = doc
        label.annotation_page = page
        label.installEventFilter(self)

    def set_mark_companion(self, *, enabled=None, kind=None):
        if enabled is not None:
            self.mark_companion["enabled"] = bool(enabled)
        if kind in TEXT_TOOLS:
            self.mark_companion["kind"] = kind
        self.owner.settings.setValue(
            "annotation/markup_text", json.dumps(self.mark_companion)
        )

    def finish_linked(self):
        store, self.linked_store = self.linked_store, None
        if store is not None:
            store.undo.endMacro()

    def defaults(self, group):
        return (
            self.draw_style
            if group == "draw"
            else self.callout_style
            if group
            else self.mark_style
        )

    def style(self, group):
        model = self.current()
        expected = "draw" if group == "draw" else "text" if group else "mark"
        if model and category(model["kind"]) == expected:
            return model
        defaults = self.defaults(group)
        if group is True and defaults["kind"] == "note":
            return {**defaults, "color": self.note_color}
        return defaults

    def change_style(self, group, key, value):
        defaults = self.defaults(group)
        if group is True and key == "color" and self.style(group)["kind"] == "note":
            self.note_color = value
            self.owner.settings.setValue("annotation/note_color", value)
        else:
            defaults[key] = value
        if not group and key == "kind" and value == "highlight":
            defaults["color"] = "#ffe13c"
        settings_key = (
            "annotation/draw"
            if group == "draw"
            else "annotation/callout"
            if group
            else "annotation/mark"
        )
        self.owner.settings.setValue(settings_key, json.dumps(defaults))
        if group and key == "kind":
            self.finish_text(True)
            self.clear()
        model = self.current()
        expected = "draw" if group == "draw" else "text" if group else "mark"
        if model and category(model["kind"]) == expected:
            changed = deepcopy(model)
            changed[key] = value
            if not group and key == "kind" and value == "highlight":
                changed["color"] = defaults["color"]
            self.commit(self.selected[0], changed, tr("修改註解樣式"))
        self.refresh_icons()

    def current(self):
        if self.selected is None:
            return None
        doc, key = self.selected
        if doc is not self.owner.current_document():
            return None
        return doc.annotation_store.items.get(key)

    def clear(self):
        self.click_timer.stop()
        self.pending_click = None
        self.pending = None
        self.requests.clear()
        self.selected = None
        self.anchor = None
        self.drag = None
        self.draft = None
        self.mark_preview = None
        self.mark_highlights = None
        self.mark_timer.stop()
        self.repaint()

    def select(self, doc, key, copy_text=False):
        if doc is not self.owner.current_document():
            return
        self.selected = (doc, key)
        self.anchor = None
        model = self.current()
        if model:
            doc.pages.set_annotation_highlight(None, None)
            doc._focus_page(model["page"])
        if model and copy_text:
            text = model.get("text", "")
            if not text.strip():
                text = next(
                    (
                        a.get("contents", "")
                        for a in doc.annotations or []
                        if a.get("annotation_id") == model["id"]
                    ),
                    "",
                )
            if text.strip():
                QApplication.clipboard().setText(text)
        self.sync_list(doc, key)
        self.repaint()

    def select_target(self, doc, page, index):
        for m in doc.annotation_store.page(page):
            if m.get("source_index") == index:
                self.select(doc, m["id"])
                self.pending = None
                return
        self.selected = None
        self.repaint()
        if page in doc.annotation_store.loaded:
            self.pending = None
            reason = doc.annotation_store.reasons.get(page, {}).get(
                index
            ) or doc.annotation_store.reasons.get(page, {}).get(str(index))
            self.owner.statusBar().showMessage(
                tr(
                    "此註解僅供檢視：{reason}",
                    reason=localize_text(reason)
                    if reason
                    else tr("尚未支援此註解類型"),
                )
            )
        else:
            self.pending = (doc.document_id, page, index)

    def loaded(self, doc, page, payload):
        geometry = payload.get("geometry")
        if geometry:
            doc.annotation_store.load(
                page,
                payload.get("editable_annotations", []),
                geometry,
                payload.get("annotation_readonly"),
            )
        if self.pending and self.pending[:2] == (doc.document_id, page):
            self.select_target(doc, page, self.pending[2])
        self.merge_list(doc)
        self.owner.navigation.refresh_annotation_tooltips(doc)
        self.repaint()

    def labels_for(self, doc):
        labels = [card.preview for card in doc.page_cards]
        viewer = self.owner._fullscreen_preview
        if viewer is not None and viewer.document is doc:
            labels += list(viewer.labels.values())
        return labels

    def repaint(self):
        for doc in self.owner.documents.values():
            for label in self.labels_for(doc):
                label.update()

    def changed(self, doc):
        if self.selected and self.selected[0] is doc and self.current() is None:
            self.selected = None
        self.merge_list(doc)
        self.owner._sync_controls()
        self.repaint()

    def merge_list(self, doc):
        if doc.annotations is None:
            return
        if not hasattr(doc, "_annotation_base"):
            doc._annotation_base = deepcopy(doc.annotations)
        result = deepcopy(doc._annotation_base)
        by_index = {(a["page"], a["index"]): a for a in doc._annotation_base}
        baseline = doc.annotation_store.baseline
        handled = {(m["page"], m["source_index"]) for m in baseline.values()}
        result = [a for a in result if (a["page"], a["index"]) not in handled]
        from repdf.annotation_graphics import transform

        for key in doc.annotation_store.order:
            if key not in doc.annotation_store.items:
                continue
            m = doc.annotation_store.items[key]
            box = transform(m["geometry"], 1, 1).mapRect(
                QRectF(
                    m["rect"][0],
                    m["rect"][1],
                    m["rect"][2] - m["rect"][0],
                    m["rect"][3] - m["rect"][1],
                )
                if m["kind"] in TEXT_TOOLS or m["kind"] in ("rectangle", "ellipse")
                else QRectF(
                    bounds(m)[0],
                    bounds(m)[1],
                    bounds(m)[2] - bounds(m)[0],
                    bounds(m)[3] - bounds(m)[1],
                )
            )
            rect = [
                max(0, min(1, v))
                for v in (box.left(), box.top(), box.right(), box.bottom())
            ]
            metadata = by_index.get((m["page"], m.get("source_index")), {})
            result.append(
                {
                    **metadata,
                    "page": m["page"],
                    "index": m.get("source_index", m["id"]),
                    "annotation_id": m["id"],
                    "kind": {
                        "highlight": "螢光筆",
                        "underline": "底線",
                        "strikeout": "刪除線",
                        "squiggly": "波浪底線",
                        "callout": "文字方塊",
                        "note": "備註",
                        "line": "直線",
                        "arrow": "箭頭",
                        "rectangle": "矩形",
                        "ellipse": "橢圓",
                        "ink": "手繪",
                    }[m["kind"]],
                    "contents": m.get("text", "") or metadata.get("contents", ""),
                    "author": metadata.get("author", ""),
                    "subject": metadata.get("subject", ""),
                    "modified": metadata.get("modified", ""),
                    "destination": {"page": m["page"], "annotation_rect": rect},
                }
            )
        result.sort(
            key=lambda a: (
                a["page"],
                a["index"] if isinstance(a["index"], int) else 1_000_000_000,
            )
        )
        if result == doc.annotations:
            return
        doc.annotations = result
        nav = self.owner.navigation
        if nav.kind == "annotations" and nav.displayed_id == doc.document_id:
            nav._remember_state()
            nav.panel.tree.clear()
            nav.items = []
            nav.annotation_groups = {}
            nav.populate(doc)
            if self.selected and self.selected[0] is doc:
                self.sync_list(doc, self.selected[1])

    def sync_list(self, doc, key):
        nav = self.owner.navigation
        if nav.kind != "annotations" or nav.displayed_id != doc.document_id:
            return
        for item, annotation in zip(nav.items, doc.annotations or []):
            if annotation.get("annotation_id") == key:
                item.parent().setExpanded(True)
                nav.panel.tree.setCurrentItem(item)
                nav.panel.tree.scrollToItem(item)
                return

    def commit(self, doc, model, label):
        model = validate(model)
        original = doc.annotation_store.items.get(model["id"])
        if original is not None:
            comparable = lambda value: {
                key: item for key, item in value.items() if key != "appearance_pdf"
            }
            if comparable(model) == comparable(original):
                return
        model["appearance_pdf"] = appearance(model)
        doc.annotation_store.change({model["id"]: model}, label)

    def paint(self, label):
        doc = label.annotation_document
        page = label.annotation_page
        geometry = doc.annotation_store.geometries.get(page)
        if not geometry:
            return
        painter = QPainter(label)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tx = transform(geometry, label.width(), label.height())
        painter.setTransform(tx)
        for model in doc.annotation_store.page(page):
            if self.draft and self.draft["id"] == model["id"]:
                continue
            paint(painter, model)
        if (
            self.draft
            and self.draft["page"] == page
            and self.draft.get("document_id", doc.document_id) == doc.document_id
        ):
            if self.text_edit is not None and self.draft["kind"] == "callout":
                paint(painter, self.draft, editing=True)
            elif self.draft["kind"] in DRAWINGS or self.draft["kind"] == "note":
                paint(painter, self.draft)
            elif self.draft.get("text", "").strip():
                paint(painter, self.draft)
            elif self.draft["kind"] == "callout":
                painter.setPen(QPen(QColor(self.draft["color"]), self.draft["width"]))
                l, b, r, t = self.draft["rect"]
                painter.drawRect(QRectF(l, b, r - l, t - b))
        painter.resetTransform()
        if self.mark_highlights and self.mark_highlights[:2] == (doc.document_id, page):
            color = label.palette().highlight().color()
            color.setAlpha(90)
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.WindingFill)
            for l, t, r, b in self.mark_highlights[2]:
                path.addRect(
                    QRectF(
                        l * label.width(),
                        t * label.height(),
                        (r - l) * label.width(),
                        (b - t) * label.height(),
                    )
                )
            painter.fillPath(path, color)
        selected = self.current() if self.selected and self.selected[0] is doc else None
        if selected and self.draft and self.draft["id"] == selected["id"]:
            selected = self.draft
        if selected and selected["page"] == page and self.text_edit is None:
            if selected["kind"] != "callout":
                l, b, r, t = bounds(selected)
                painter.setPen(QPen(label.palette().highlight().color(), 1.5))
                painter.drawRect(tx.mapRect(QRectF(l, b, r - l, t - b)))
            painter.setPen(QPen(label.palette().highlight().color(), 1.5))
            for point in self.handles(selected, tx).values():
                painter.setBrush(label.palette().base())
                painter.drawRect(QRectF(point.x() - 4, point.y() - 4, 8, 8))
        if self.anchor and self.anchor[:2] == (doc.document_id, page):
            point = tx.map(QPointF(*self.anchor[2]))
            painter.setPen(QPen(QColor("#ff0000"), 1))
            painter.drawEllipse(point, 4, 4)
        painter.end()

    def handles(self, m, tx):
        if m["kind"] in ("line", "arrow"):
            return {
                "start": tx.map(QPointF(*m["points"][:2])),
                "end": tx.map(QPointF(*m["points"][2:])),
            }
        if m["kind"] not in DRAWINGS and m["kind"] != "callout":
            return {}
        l, b, r, t = rect_for(m)
        points = [("lb", (l, b)), ("lt", (l, t)), ("rb", (r, b)), ("rt", (r, t))]
        if m["kind"] == "callout":
            points.insert(0, ("anchor", m["leader"][:2]))
        return {name: tx.map(QPointF(*point)) for name, point in points}

    def hit(self, label, position):
        doc = label.annotation_document
        geometry = doc.annotation_store.geometries.get(label.annotation_page)
        if not geometry:
            return None, None
        tx = transform(geometry, label.width(), label.height())
        current = self.current() if self.selected and self.selected[0] is doc else None
        if current and current["page"] == label.annotation_page:
            for name, point in self.handles(current, tx).items():
                if (position - point).manhattanLength() < 11:
                    return current, name
        for m in reversed(doc.annotation_store.page(label.annotation_page)):
            if m["kind"] in ("line", "arrow", "ink"):
                paths = m["paths"] if m["kind"] == "ink" else [m["points"]]
                for path in paths:
                    points = [
                        tx.map(QPointF(*path[i : i + 2]))
                        for i in range(0, len(path), 2)
                    ]
                    for a, b in zip(points, points[1:]):
                        dx, dy = b.x() - a.x(), b.y() - a.y()
                        ratio = max(
                            0,
                            min(
                                1,
                                (
                                    (position.x() - a.x()) * dx
                                    + (position.y() - a.y()) * dy
                                )
                                / max(1, dx * dx + dy * dy),
                            ),
                        )
                        if (
                            position - QPointF(a.x() + ratio * dx, a.y() + ratio * dy)
                        ).manhattanLength() < max(8, m["width"] * 2):
                            return m, "body"
                continue
            if m["kind"] == "callout":
                points = [
                    tx.map(QPointF(*m["leader"][i : i + 2]))
                    for i in range(0, len(m["leader"]), 2)
                ]
                if (position - points[0]).manhattanLength() < 11:
                    return m, "anchor"
                for a, b in zip(points, points[1:]):
                    dx, dy = b.x() - a.x(), b.y() - a.y()
                    ratio = max(
                        0,
                        min(
                            1,
                            ((position.x() - a.x()) * dx + (position.y() - a.y()) * dy)
                            / max(1, dx * dx + dy * dy),
                        ),
                    )
                    nearest = QPointF(a.x() + ratio * dx, a.y() + ratio * dy)
                    if (position - nearest).manhattanLength() < 8:
                        return m, "body"
            l, b, r, t = (
                rect_for(m)
                if m["kind"] in TEXT_TOOLS or m["kind"] in DRAWINGS
                else bounds(m)
            )
            if (
                tx.mapRect(QRectF(l, b, r - l, t - b))
                .adjusted(-3, -3, 3, 3)
                .contains(position)
            ):
                return m, "body"
        return None, None

    def hover_cursor(self, label, model, handle):
        if model and (model["kind"] in TEXT_TOOLS or model["kind"] in DRAWINGS):
            if handle in ("anchor", "start", "end"):
                return Qt.CursorShape.PointingHandCursor
            if handle == "body":
                return Qt.CursorShape.SizeAllCursor
            tx = transform(model["geometry"], label.width(), label.height())
            l, b, r, t = rect_for(model)
            corner = self.handles(model, tx)[handle]
            center = tx.map(QPointF((l + r) / 2, (b + t) / 2))
            return (
                Qt.CursorShape.SizeFDiagCursor
                if (corner.x() - center.x()) * (corner.y() - center.y()) > 0
                else Qt.CursorShape.SizeBDiagCursor
            )
        if model:
            return Qt.CursorShape.PointingHandCursor
        if self.mode() == "mark":
            return Qt.CursorShape.IBeamCursor
        if self.mode() in ("callout", "draw"):
            return Qt.CursorShape.CrossCursor
        return (
            Qt.CursorShape.OpenHandCursor
            if label.draggable
            else Qt.CursorShape.ArrowCursor
        )

    def usable(self, label):
        return (
            self.owner.current_document() is label.annotation_document
            and not self.owner._export_running
            and not self.owner.print_controller.busy
            and not self.owner._closing
        )

    def eventFilter(self, watched, event):
        if (
            self.dismiss_click
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.dismiss_click = False
            return True
        if (
            self.text_edit is not None
            and isinstance(watched, QWidget)
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
            and watched is not self.text_edit
            and not self.text_edit.isAncestorOf(watched)
        ):
            surface = watched
            while surface is not None and not hasattr(surface, "annotation_document"):
                surface = surface.parentWidget()
            if surface is not None:
                # This click completes the edit; a subsequent click may create another.
                self.dismiss_click = True
                self.drag = None
                self.finish_text(True)
                return True
        if watched is self.text_edit:
            if event.type() == QEvent.Type.InputMethod:
                watched.setProperty("preeditText", event.preeditString())
                edit = watched
                QTimer.singleShot(
                    0, lambda: self.fit_text() if self.text_edit is edit else None
                )
            if event.type() == QEvent.Type.ShortcutOverride and (
                event.matches(QKeySequence.StandardKey.Save)
                or event.matches(QKeySequence.StandardKey.SaveAs)
            ):
                event.accept()
                return True
            if event.type() == QEvent.Type.KeyPress:
                if event.matches(QKeySequence.StandardKey.Save) or event.matches(
                    QKeySequence.StandardKey.SaveAs
                ):
                    save_as = event.matches(QKeySequence.StandardKey.SaveAs)
                    self.finish_text(True)
                    self.owner.saving.choose(save_as=save_as)
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self.finish_text(False)
                    return True
                if (
                    event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                ):
                    self.finish_text(True)
                    return True
            if event.type() == QEvent.Type.FocusOut:
                edit = watched
                QTimer.singleShot(
                    0,
                    lambda: self.finish_text(True) if self.text_edit is edit else None,
                )
            return False
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            if not isinstance(watched, QWidget) or watched.window() not in (
                self.owner,
                self.owner._fullscreen_preview,
            ):
                return False
            focus = QApplication.focusWidget()
            if (
                isinstance(focus, (QLineEdit, QPlainTextEdit))
                or not self.owner.current_document()
            ):
                return False
            tree = self.owner.navigation.panel.tree
            copy_text = (
                event.matches(QKeySequence.StandardKey.Copy)
                and self.current() is not None
                and focus is not tree
                and not (focus and tree.isAncestorOf(focus))
            )
            undo = event.matches(QKeySequence.StandardKey.Undo)
            redo = event.matches(QKeySequence.StandardKey.Redo)
            delete = event.key() == Qt.Key.Key_Delete and self.current() is not None
            escape = event.key() == Qt.Key.Key_Escape and (
                self.anchor is not None
                or self.selected is not None
                or self.drag is not None
                or self.draft is not None
            )
            if copy_text or undo or redo or delete or escape:
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                    return True
                doc = self.owner.current_document()
                if copy_text:
                    model = self.current()
                    text = model.get("text", "") or next(
                        (
                            a.get("contents", "")
                            for a in doc.annotations or []
                            if a.get("annotation_id") == model["id"]
                        ),
                        "",
                    )
                    if text.strip():
                        QApplication.clipboard().setText(text)
                        self.owner.statusBar().showMessage(
                            tr("已複製 {p0} 個字元到剪貼簿", p0=len(text))
                        )
                elif undo:
                    doc.annotation_store.undo.undo()
                elif redo:
                    doc.annotation_store.undo.redo()
                elif delete:
                    doc.annotation_store.change(
                        {self.current()["id"]: None}, tr("刪除註解")
                    )
                else:
                    self.clear()
                return True
        if not hasattr(watched, "annotation_document") or not self.usable(watched):
            return False
        label = watched
        doc = label.annotation_document
        page = label.annotation_page
        geometry = doc.annotation_store.geometries.get(page)
        if label.text_mode:
            return False
        if not geometry:
            if self.mode() and event.type() in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonRelease,
            ):
                if event.type() == QEvent.Type.MouseButtonPress:
                    self.owner.statusBar().showMessage(tr("頁面正在載入，請稍候…"))
                return True
            return False
        kind = event.type()
        if kind not in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonDblClick,
        ):
            return False
        position = event.position()
        tx = transform(geometry, label.width(), label.height())
        inverse, _ = tx.inverted()
        point = inverse.map(position)
        gl, gb, gr, gt = geometry["box"]
        point = QPointF(max(gl, min(gr, point.x())), max(gb, min(gt, point.y())))
        if kind == QEvent.Type.MouseButtonDblClick:
            model, _ = self.hit(label, position)
            if model and model["kind"] in TEXT_TOOLS:
                self.click_timer.stop()
                self.pending_click = None
                self.drag = None
                if model["kind"] == "note":
                    self.edit_note(label, deepcopy(model))
                else:
                    self.begin_text(label, deepcopy(model))
                return True
        if (
            kind == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.click_timer.stop()
            self.pending_click = None
            model, handle = self.hit(label, position)
            if model:
                label.setCursor(self.hover_cursor(label, model, handle))
                self.select(doc, model["id"])
                self.drag = (label, position, point, deepcopy(model), handle)
                return True
            if self.mode() == "callout":
                self.drag = (label, position, point, None, "new")
                return True
            if self.mode() == "draw":
                self.drag = (label, position, point, None, "draw")
                self.draft = None
                return True
            if self.mode() == "mark":
                self.mark_highlights = None
                self.drag = (label, position, point, None, "mark")
                return True
            if self.selected is not None:
                self.clear()
        if kind == QEvent.Type.MouseMove:
            if self.drag is None:
                model, handle = self.hit(label, position)
                label.setCursor(self.hover_cursor(label, model, handle))
                if model:
                    label.setToolTip(
                        "<qt>"
                        + html_escape(tr(KINDS.get(model["kind"], "註解")))
                        + (
                            "<br>"
                            + html_escape(model.get("text", "")).replace("\n", "<br>")
                            if model.get("text")
                            else ""
                        )
                        + "</qt>"
                    )
                return bool(model or self.mode())
            if self.drag[0] is not label:
                return False
            _, start, origin, model, handle = self.drag
            if handle == "draw":
                self.update_drawing(label, origin, point)
                return True
            if handle == "mark" or (model and model["kind"] in MARKUPS):
                if self.mode() == "mark":
                    self.mark_preview = (label, start, position)
                    if not self.mark_timer.isActive():
                        self.mark_timer.start()
                    self.repaint()
                return True
            if model and (model["kind"] in DRAWINGS or model["kind"] == "note"):
                self.draft = self.drag_drawing(model, handle, origin, point)
                self.repaint()
                return True
            if model:
                m = deepcopy(model)
                dx, dy = point.x() - origin.x(), point.y() - origin.y()
                if handle == "body":
                    l, b, r, t = m["rect"]
                    dx = max(gl - l, min(gr - r, dx))
                    dy = max(gb - b, min(gt - t, dy))
                    m = moved(m, dx, dy)
                elif handle == "anchor":
                    m["leader"][:2] = [point.x(), point.y()]
                else:
                    l, b, r, t = m["rect"]
                    minimum_height = self.minimum_text_height(m)
                    min_width, min_height = (
                        (minimum_height, 12)
                        if m.get("text_rotation", 0) in (90, 270)
                        else (12, minimum_height)
                    )
                    if "l" in handle:
                        l = max(gl, min(point.x(), r - min_width))
                    if "r" in handle:
                        r = min(gr, max(point.x(), l + min_width))
                    if "b" in handle:
                        b = max(gb, min(point.y(), t - min_height))
                    if "t" in handle:
                        t = min(gt, max(point.y(), b + min_height))
                    m["rect"] = [l, b, r, t]
                    m["leader"][-2:] = [l, (b + t) / 2]
            else:
                return True
            self.draft = reroute(m)
            self.repaint()
            return True
        if (
            kind == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            if self.drag is None:
                return bool(self.anchor)
            if self.drag[0] is not label:
                return False
            _, start, origin, model, handle = self.drag
            self.drag = None
            self.mark_preview = None
            if handle == "draw":
                if (
                    position - start
                ).manhattanLength() < QApplication.startDragDistance():
                    self.draft = None
                    self.repaint()
                    return True
                self.update_drawing(label, origin, point)
                drawing, self.draft = self.draft, None
                try:
                    drawing = validate(drawing)
                except ValueError:
                    self.repaint()
                    return True
                self.commit(doc, drawing, tr("新增繪圖註解"))
                self.select(doc, drawing["id"])
                return True
            if handle == "new":
                if self.callout_style["kind"] == "note":
                    self.edit_note(label, self.new_note(label, origin))
                else:
                    self.begin_text(label, self.new_callout(label, origin))
                self.repaint()
                return True
            distance = (position - start).manhattanLength()
            if handle == "mark" or (
                model
                and model["kind"] in MARKUPS
                and distance >= QApplication.startDragDistance()
                and self.mode() == "mark"
            ):
                self.request_mark(label, start, position)
                return True
            if distance < QApplication.startDragDistance() and model:
                self.draft = None
                self.select(doc, model["id"], copy_text=True)
                if (
                    model["kind"] in TEXT_TOOLS
                    and not self.owner.navigation.panel.isVisible()
                ):
                    # Opening the sidebar resizes the page and breaks the second
                    # click's widget/coordinates. Wait until a double click is ruled out.
                    self.pending_click = (doc.document_id, model["id"])
                    self.click_timer.start(QApplication.doubleClickInterval())
                else:
                    self.show_annotation_list(doc, model["id"])
                return True
            if self.draft:
                m = self.draft
                self.draft = None
                if handle == "new":
                    self.anchor = None
                    self.begin_text(label, m)
                else:
                    if m["kind"] in DRAWINGS:
                        try:
                            validate(m)
                        except ValueError:
                            self.repaint()
                            return True
                    self.commit(doc, m, tr("移動註解"))
            self.repaint()
            return True
        return False

    def update_drawing(self, label, origin, point):
        doc, page = label.annotation_document, label.annotation_page
        geometry = doc.annotation_store.geometries[page]
        end = (point.x(), point.y())
        if self.draw_style["kind"] == "ink" and self.draft:
            path = self.draft["paths"][0]
            if (abs(path[-2] - end[0]) + abs(path[-1] - end[1])) >= 0.75:
                if len(path) >= 20000:
                    # Bound long strokes so editable JSON remains below its import limit.
                    points = [path[i : i + 2] for i in range(0, len(path), 2)]
                    path[:] = [value for point in points[::2] for value in point]
                path.extend(end)
        else:
            previous_id = self.draft["id"] if self.draft else None
            self.draft = new_drawing(
                self.draw_style, page, geometry, (origin.x(), origin.y()), end
            )
            if previous_id:
                self.draft["id"] = previous_id
        self.repaint()

    def drag_drawing(self, model, handle, origin, point):
        m = deepcopy(model)
        gl, gb, gr, gt = m["geometry"]["box"]
        l, b, r, t = rect_for(m)
        if handle == "body":
            dx = max(gl - l, min(gr - r, point.x() - origin.x()))
            dy = max(gb - b, min(gt - t, point.y() - origin.y()))
            return moved(m, dx, dy)
        if handle in ("start", "end"):
            offset = 0 if handle == "start" else 2
            m["points"][offset : offset + 2] = [point.x(), point.y()]
            return m
        if "l" in handle:
            l = max(gl, min(point.x(), r - 2))
        if "r" in handle:
            r = min(gr, max(point.x(), l + 2))
        if "b" in handle:
            b = max(gb, min(point.y(), t - 2))
        if "t" in handle:
            t = min(gt, max(point.y(), b + 2))
        return resize(m, [l, b, r, t])

    def new_note(self, label, point):
        geometry = label.annotation_document.annotation_store.geometries[
            label.annotation_page
        ]
        gl, gb, gr, gt = geometry["box"]
        width, height = min(24, gr - gl), min(24, gt - gb)
        l, b = (
            max(gl, min(gr - width, point.x())),
            max(gb, min(gt - height, point.y() - height)),
        )
        return {
            **deepcopy(self.callout_style),
            "kind": "note",
            "color": self.note_color,
            "id": "repdf-" + uuid4().hex,
            "page": label.annotation_page,
            "geometry": geometry,
            "rect": [l, b, l + width, b + height],
            "text": "",
        }

    def edit_note(self, label, model):
        self.finish_text(True)
        self.click_timer.stop()
        self.pending_click = None
        self.drag = None
        self.draft = model
        self.repaint()
        dialog = QDialog(self.owner._fullscreen_preview or self.owner)
        dialog.setWindowTitle(tr("便利貼"))
        dialog.resize(420, 280)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(model.get("text", ""))
        text.setAccessibleName(tr("註解文字"))
        layout.addWidget(text)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setEnabled(bool(text.toPlainText().strip()))
        text.textChanged.connect(
            lambda: save.setEnabled(bool(text.toPlainText().strip()))
        )
        layout.addWidget(buttons)
        text.setFocus()
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.draft = None
        if accepted and text.toPlainText().strip():
            model["text"] = text.toPlainText()
            doc = label.annotation_document
            self.commit(doc, model, tr("編輯便利貼"))
            self.select(doc, model["id"])
        dialog.deleteLater()
        self.finish_linked()
        self.repaint()

    def open_clicked_annotation(self):
        pending = self.pending_click
        self.pending_click = None
        if pending is None or self.text_edit is not None or self.drag is not None:
            return
        doc = self.owner.documents.get(pending[0])
        if doc is self.owner.current_document() and self.selected == (doc, pending[1]):
            self.show_annotation_list(doc, pending[1])

    def show_annotation_list(self, doc, key):
        nav = self.owner.navigation
        nav.open(
            "annotations", keep_fullscreen=self.owner._fullscreen_preview is not None
        )
        nav.narrow_results = False
        nav.layout()
        self.merge_list(doc)
        for item, annotation in zip(nav.items, doc.annotations or []):
            if annotation.get("annotation_id") == key:
                item.parent().setExpanded(True)
                nav.panel.tree.setCurrentItem(item)
                nav.panel.tree.scrollToItem(item)
                break

    @staticmethod
    def minimum_text_height(model):
        font = QFont(model.get("font", QApplication.font().family()))
        font.setPixelSize(round(model["size"]))
        return QFontMetricsF(font).height() + 12

    def new_callout(self, label, target, *, style=None, prefer_above=False):
        geometry = label.annotation_document.annotation_store.geometries[
            label.annotation_page
        ]
        model = {
            **deepcopy(self.callout_style if style is None else style),
            "kind": "callout",
            "id": "repdf-" + uuid4().hex,
            "page": label.annotation_page,
            "geometry": geometry,
            "text": "",
            "font": QApplication.font().family(),
            "text_rotation": geometry["rotation"],
        }
        # Lay out in upright page coordinates, including rotated/cropped pages.
        l, b, r, t = geometry["box"]
        width, height = r - l, t - b
        if geometry["rotation"] in (90, 270):
            width, height = height, width
        tx = transform(geometry, width, height)
        inverse, _ = tx.inverted()
        point = tx.map(target)
        box_width = min(max(180, model["size"] * 6 + 12), width)
        box_height = min(max(48, self.minimum_text_height(model)), height)
        gap = 24
        candidates = [
            QRectF(point.x() + gap, point.y() - box_height / 2, box_width, box_height),
            QRectF(
                point.x() - gap - box_width,
                point.y() - box_height / 2,
                box_width,
                box_height,
            ),
            QRectF(point.x() - box_width / 2, point.y() + gap, box_width, box_height),
            QRectF(
                point.x() - box_width / 2,
                point.y() - gap - box_height,
                box_width,
                box_height,
            ),
        ]
        if prefer_above:
            candidates = [candidates[3], *candidates[:3]]
        boxes = []
        for candidate in candidates:
            candidate.moveLeft(max(0, min(width - box_width, candidate.left())))
            candidate.moveTop(max(0, min(height - box_height, candidate.top())))
            dx = max(candidate.left() - point.x(), 0, point.x() - candidate.right())
            dy = max(candidate.top() - point.y(), 0, point.y() - candidate.bottom())
            boxes.append((dx * dx + dy * dy, candidate))
        # Prefer a full gap, otherwise retain as much separation as the page allows.
        rectangle = next(
            (rect for distance, rect in boxes if distance >= gap * gap),
            max(boxes, key=lambda item: item[0])[1],
        )
        rect = inverse.mapRect(rectangle)
        model["rect"] = [rect.left(), rect.top(), rect.right(), rect.bottom()]
        model["leader"] = [target.x(), target.y(), rect.left(), rect.center().y()]
        return reroute(model)

    def begin_text(self, label, model):
        self.click_timer.stop()
        self.pending_click = None
        self.drag = None
        self.finish_text(True)
        self.edit_model = (label.annotation_document, model)
        self.draft = model
        l, b, r, t = model["rect"]
        tx = transform(model["geometry"], label.width(), label.height())
        rectangle = tx.mapRect(QRectF(l, b, r - l, t - b)).toAlignedRect()
        edit = QPlainTextEdit(label)
        edit.setGeometry(rectangle)
        edit.setPlainText(model["text"])
        edit.setProperty(
            "minimumTextWidth",
            t - b if model["geometry"]["rotation"] in (90, 270) else r - l,
        )
        edit.setProperty("preeditText", "")
        font = QFont(model.get("font", QApplication.font().family()))
        font.setPixelSize(max(1, round(model["size"] * abs(tx.m11() or tx.m12()))))
        edit.setFont(font)
        edit.document().setDocumentMargin(4 * abs(tx.m11() or tx.m12()))
        edit.setStyleSheet(
            "QPlainTextEdit { color: palette(text); background: palette(base); "
            "border: 1px solid palette(highlight); border-radius: 6px; padding: 0; "
            "selection-background-color: palette(highlight); "
            "selection-color: palette(highlighted-text); }"
        )
        edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit = edit
        edit.installEventFilter(self)
        edit.textChanged.connect(self.fit_text)
        edit.show()
        edit.setFocus()
        cursor = edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        edit.setTextCursor(cursor)

    def fit_text(self):
        edit = self.text_edit
        if edit is None:
            return
        _, model = self.edit_model
        geometry = model["geometry"]
        label = edit.parentWidget()
        gl, gb, gr, gt = geometry["box"]
        page_width, page_height = gr - gl, gt - gb
        if geometry["rotation"] in (90, 270):
            page_width, page_height = page_height, page_width
        upright = transform(geometry, page_width, page_height)
        inverse, _ = upright.inverted()
        l, b, r, t = model["rect"]
        rectangle = upright.mapRect(QRectF(l, b, r - l, t - b))
        text = edit.toPlainText()
        document = QTextDocument()
        font = QFont(model.get("font", QApplication.font().family()))
        font.setPixelSize(round(model["size"]))
        document.setDefaultFont(font)
        document.setDocumentMargin(4)
        preedit = edit.property("preeditText") or ""
        cursor = edit.textCursor()
        # Include IME composition in layout without putting uncommitted text in the PDF.
        # Cursor positions are UTF-16 offsets, unlike Python string indexes.
        encoded = text.encode("utf-16-le")
        start, end = cursor.selectionStart() * 2, cursor.selectionEnd() * 2
        measured_text = (
            (
                encoded[:start].decode("utf-16-le")
                + preedit
                + encoded[end:].decode("utf-16-le")
            )
            if preedit
            else text
        )
        document.setPlainText(measured_text)
        minimum = min(page_width, max(48, edit.property("minimumTextWidth")))
        maximum = min(page_width, max(minimum, page_width - rectangle.left()))
        width = min(maximum, max(minimum, document.idealWidth() + 8))
        document.setTextWidth(width)
        height = min(
            page_height,
            max(self.minimum_text_height(model), document.size().height() + 4),
        )
        rectangle.setSize(QSizeF(width, height))
        rectangle.moveLeft(max(0, min(page_width - width, rectangle.left())))
        rectangle.moveTop(max(0, min(page_height - height, rectangle.top())))
        pdf_rect = inverse.mapRect(rectangle)
        model["rect"] = [
            pdf_rect.left(),
            pdf_rect.top(),
            pdf_rect.right(),
            pdf_rect.bottom(),
        ]
        model["text"] = text
        routed = reroute(model)
        model.update(routed)
        self.draft = model
        tx = transform(geometry, label.width(), label.height())
        edit.setGeometry(tx.mapRect(pdf_rect).toAlignedRect())
        self.repaint()

    def finish_text(self, accept):
        edit = self.text_edit
        if edit is None:
            return
        doc, model = self.edit_model
        text = edit.toPlainText()
        self.text_edit = None
        self.edit_model = None
        self.draft = None
        edit.removeEventFilter(self)
        edit.hide()
        edit.deleteLater()
        if accept and text.strip():
            model["text"] = text
            self.commit(doc, model, tr("編輯文字註解"))
            self.select(doc, model["id"])
        self.finish_linked()
        self.repaint()

    def add_mark_companion(self, doc, markup, request):
        page = markup["page"]
        viewer = self.owner._fullscreen_preview
        if viewer is not None and viewer.document is doc:
            if page not in viewer.labels:
                viewer.show_page(page)
            label = viewer.labels[page]
        else:
            label = doc.pages.ensure_page(page).preview
        target = selection_top_center(markup["quads"], markup["geometry"])
        kind = request[4]["kind"]
        if kind == "callout":
            model = self.new_callout(label, target, style=request[5], prefer_above=True)
            self.begin_text(label, model)
            if viewer is None:
                doc.scroll_area.ensureWidgetVisible(self.text_edit, 8, 8)
        else:
            model = self.new_note(label, target)
            model["color"] = request[6]
            geometry = markup["geometry"]
            l, b, r, t = geometry["box"]
            width, height = (
                (t - b, r - l) if geometry["rotation"] in (90, 270) else (r - l, t - b)
            )
            tx = transform(geometry, width, height)
            point = tx.map(target)
            w, h = min(24, width), min(24, height)
            rect = QRectF(
                max(0, min(width - w, point.x() - w / 2)),
                max(0, min(height - h, point.y() - h - 4)),
                w,
                h,
            )
            inverse, _ = tx.inverted()
            rect = inverse.mapRect(rect)
            model["rect"] = [rect.left(), rect.top(), rect.right(), rect.bottom()]
            self.edit_note(label, model)

    def preview_mark(self):
        if self.mark_preview and self.drag and self.mode() == "mark":
            self.request_mark(*self.mark_preview, preview=True)

    def request_mark(self, label, start, end, *, preview=False):
        if not preview:
            self.mark_timer.stop()
            self.mark_highlights = None
        self.owner._next_generation += 1
        generation = self.owner._next_generation
        self.requests = {
            generation: (
                label.annotation_document.document_id,
                label.annotation_page,
                deepcopy(self.mark_style),
                preview,
                deepcopy(self.mark_companion),
                deepcopy(self.callout_style),
                self.note_color,
            )
        }
        self.owner.render_service.request_text(
            label.annotation_document.source_path,
            label.annotation_page,
            (start.x() / label.width(), start.y() / label.height()),
            (end.x() / label.width(), end.y() / label.height()),
            generation,
            -6_000_000 - label.annotation_document.document_id,
            password=label.annotation_document.password,
        )

    def receive(self, payload):
        request = self.requests.get(payload.get("generation"))
        if request is None:
            return False
        if payload["type"] in ("done", "error"):
            self.requests.pop(payload["generation"], None)
        doc = self.owner.documents.get(request[0])
        if (
            doc is None
            or doc is not self.owner.current_document()
            or self.mode() != "mark"
        ):
            return True
        if payload["type"] == "error":
            self.owner.statusBar().showMessage(
                tr("無法新增畫線：{reason}", reason=payload.get("message", ""))
            )
        if payload["type"] == "text":
            if request[3]:
                if self.drag is not None:
                    self.mark_highlights = (
                        request[0],
                        request[1],
                        payload.get("rects", []),
                    )
                    self.repaint()
                return True
            quads = payload.get("quads", [])
            if not quads:
                self.owner.statusBar().showMessage(tr("此區域沒有可選取的文字"))
                return True
            # Join adjacent glyph boxes on each PDF text line.
            lines = []
            for q in quads:
                l, b, r, t = q[4], q[5], q[2], q[1]
                if (
                    lines
                    and abs(lines[-1][3] - t) < max(1, (t - b) * 0.3)
                    and l - lines[-1][2] < max(4, (t - b) * 3)
                ):
                    old = lines[-1]
                    lines[-1] = [
                        min(l, old[0]),
                        min(b, old[1]),
                        max(r, old[2]),
                        max(t, old[3]),
                    ]
                else:
                    lines.append([l, b, r, t])
            m = {
                **request[2],
                "id": "repdf-" + uuid4().hex,
                "page": request[1],
                "geometry": doc.annotation_store.geometries[request[1]],
                "text": payload.get("text", ""),
                "quads": [[l, t, r, t, l, b, r, b] for l, b, r, t in lines],
            }
            if request[4]["enabled"]:
                self.finish_text(True)
                self.finish_linked()
                doc.annotation_store.undo.beginMacro(tr("新增畫線與文字註解"))
                self.linked_store = doc.annotation_store
            try:
                self.commit(doc, m, tr("新增文字畫線"))
                self.select(doc, m["id"])
                if request[4]["enabled"]:
                    self.add_mark_companion(doc, m, request)
            except Exception:
                self.finish_linked()
                raise
        return True
