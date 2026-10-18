"""Render documentation assets on opaque tiles readable in any Markdown theme.

Run with: uv run python scripts/render_doc_icons.py
"""

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QCheckBox, QHBoxLayout, QLabel, QSlider, QWidget

from repdf.app import configure_application
from repdf.icons import toolbar_icon
from repdf.theme import ThemeController


OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "images"
BACKGROUND = QColor("#f5f6f8")
BORDER = QColor("#c4c7cd")
SCALE = 2
ICON_KINDS = {
    "open": "open", "export": "export", "split": "split",
    "copy-text": "copy_text", "ocr-region": "ocr_region", "extract-image": "extract_image",
    "fit": "fit", "fullscreen": "fullscreen", "fullscreen-spread": "fullscreen_spread",
    "fullscreen-cover": "fullscreen_cover", "language-system": "language_system",
    "language-zh": "language_zh", "language-en": "language_en",
    "theme-system": "theme_system", "theme-light": "theme_light", "theme-dark": "theme_dark",
}


def tile(width, height):
    pixmap = QPixmap(width * SCALE, height * SCALE)
    pixmap.fill(BACKGROUND)
    painter = QPainter(pixmap)
    painter.scale(SCALE, SCALE)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(BORDER, 1))
    painter.setBrush(BACKGROUND)
    painter.drawRoundedRect(QRectF(.5, .5, width - 1, height - 1), 3, 3)
    return pixmap, painter


def save_widget(widget, name):
    widget.ensurePolished()
    widget.adjustSize()
    width, height = widget.width() + 12, widget.height() + 8
    pixmap, painter = tile(width, height)
    painter.translate(6, 4)
    widget.render(painter, QPoint())
    painter.end()
    save(pixmap, name)


def save(pixmap, name):
    if not pixmap.save(str(OUTPUT / f"toolbar-{name}.png")):
        raise RuntimeError(f"Could not save documentation icon: {name}")


def main():
    app = QApplication([])
    configure_application(app)
    theme = ThemeController(app, "light")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, kind in ICON_KINDS.items():
        pixmap, painter = tile(24, 24)
        toolbar_icon(kind).paint(painter, QRect(2, 2, 20, 20))
        painter.end()
        save(pixmap, name)
    for name, label in (("odd", "單數頁"), ("even", "雙數頁")):
        checkbox = QCheckBox(label)
        checkbox.setTristate(True)
        checkbox.setCheckState(Qt.CheckState.Unchecked if name == "odd" else Qt.CheckState.PartiallyChecked)
        save_widget(checkbox, name)
    zoom = QWidget()
    layout = QHBoxLayout(zoom)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    layout.addWidget(QLabel("100%"))
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(25, 200)
    slider.setValue(100)
    slider.setFixedWidth(150)
    layout.addWidget(slider)
    save_widget(zoom, "zoom")
    print(f"Rendered {len(ICON_KINDS) + 3} documentation images in {OUTPUT}")


if __name__ == "__main__":
    main()
