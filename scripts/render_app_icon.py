"""Render the vector app icon into runtime PNG, ICO and a size preview."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image, ImageDraw

from repdf.icon_layout import fitted_icon


def main():
    root = Path(__file__).resolve().parents[1]
    assets = root / 'src/repdf/assets'
    renderer = QSvgRenderer(str(assets / 'repdf.svg'))
    if not renderer.isValid():
        raise ValueError('Invalid application SVG')
    image = QImage(1024, 1024, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(assets / 'repdf.png')):
        raise OSError('Could not save app icon')
    icon = fitted_icon(assets / 'repdf.png')
    sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
    icon.save(assets / 'repdf.ico', format='ICO', sizes=[(n, n) for n in sizes])
    preview = Image.new('RGB', (800, 260), '#f3f4f6')
    draw = ImageDraw.Draw(preview)
    x = 16
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        sample = icon.resize((size, size), Image.Resampling.LANCZOS)
        preview.paste(sample, (x, 10), sample)
        draw.text((x, min(245, size + 20)), str(size), fill='#334155')
        x += size + 18
    target = root / 'output/app-icon-preview.png'
    target.parent.mkdir(exist_ok=True)
    preview.save(target)


if __name__ == '__main__':
    main()
