"""Consistent optical size for window, taskbar and packaged application icons."""

from PIL import Image


def fitted_icon(source, size=1024):
    image = Image.open(source).convert("RGBA")
    # Ignore almost-transparent shadow pixels when measuring visual bounds.
    bounds = (
        image.getchannel("A").point(lambda alpha: 255 if alpha >= 32 else 0).getbbox()
    )
    if bounds:
        image = image.crop(bounds)
    available = round(size * 0.92)
    ratio = available / max(image.size)
    image = image.resize(
        (round(image.width * ratio), round(image.height * ratio)),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size))
    canvas.alpha_composite(
        image, ((size - image.width) // 2, (size - image.height) // 2)
    )
    return canvas
