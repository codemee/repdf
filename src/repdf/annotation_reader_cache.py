"""Bounded, backend-only annotation metadata cache."""

from collections import OrderedDict
from pathlib import Path
from pypdf import PdfReader
from repdf.annotation_data import read_models

_cache = OrderedDict()


def models_for_page(source, password, page):
    path = Path(source).resolve()
    stat = path.stat()
    key = (path, stat.st_size, stat.st_mtime_ns, password)
    if key not in _cache:
        stream = path.open("rb")
        try:
            _cache[key] = (PdfReader(stream, password=password), {})
        except Exception:
            stream.close()
            raise
    _cache.move_to_end(key)
    while len(_cache) > 3:
        _, (reader, _) = _cache.popitem(last=False)
        reader.stream.close()
    reader, pages = _cache[key]
    if page not in pages:
        pages[page] = read_models(reader, page)
    return pages[page]


def release(source):
    path = Path(source).resolve()
    for key in list(_cache):
        if key[0] == path:
            reader, _ = _cache.pop(key)
            reader.stream.close()


def clear():
    for reader, _ in _cache.values():
        reader.stream.close()
    _cache.clear()
