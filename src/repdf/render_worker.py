from __future__ import annotations

import json
import socket
import sys
from collections import OrderedDict
from pathlib import Path
from typing import TextIO

import pypdfium2 as pdfium

from repdf.ocr import OcrError, recognize_region, recognize_selection, suspicious_text
from repdf.images import extract_clicked_image
from repdf.pdf_navigation import read_bookmarks, read_page_label, read_page_links, resolve_destination


class PdfDocumentCache:
    """PDFium handles stay on the backend's single execution thread."""

    def __init__(self, limit=3):
        self.limit = limit
        self.documents = OrderedDict()

    def get(self, source, password=None):
        path = Path(source).resolve()
        stat = path.stat()
        key = (path, stat.st_size, stat.st_mtime_ns, password)
        if key not in self.documents:
            self.documents[key] = pdfium.PdfDocument(str(path), password=password)
        self.documents.move_to_end(key)
        while len(self.documents) > self.limit:
            _, document = self.documents.popitem(last=False)
            document.close()
        return self.documents[key]

    def release(self, source):
        path = Path(source).resolve()
        for key in list(self.documents):
            if key[0] == path:
                self.documents.pop(key).close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        for document in self.documents.values():
            document.close()
        self.documents.clear()


def render_document(
    source: Path, scale: float, output_dir: Path, generation: int,
    output_stream: TextIO | None = None,
    pages: list[int] | None = None,
    password: str | None = None,
    document=None,
) -> None:
    own_document = document is None
    if own_document:
        document = pdfium.PdfDocument(str(source), password=password)
    try:
        indices = range(len(document)) if pages is None else pages
        for page_index in indices:
            if not isinstance(page_index, int) or not 0 <= page_index < len(document):
                raise ValueError("Invalid preview page index")
            page = document[page_index]
            try:
                width_points, height_points = page.get_size()
                links = read_page_links(document, page)
                page_label = read_page_label(document, page_index)
                bitmap = page.render(scale=max(scale, 0.1))
                try:
                    image = bitmap.to_pil().convert("RGB")
                    output = output_dir / f"g{generation}-p{page_index}.png"
                    image.save(output, "PNG")
                finally:
                    bitmap.close()
            finally:
                page.close()
            print(json.dumps({
                "type": "page", "generation": generation,
                "page": page_index, "path": str(output),
                "width_points": width_points, "height_points": height_points,
                "links": links,
                "page_label": page_label,
            }), file=output_stream, flush=True)
    finally:
        if own_document:
            document.close()


def extract_selection_result(source: Path, page_index: int, start: list[float],
                             end: list[float], *, allow_ocr: bool = False,
                             on_ocr=None, password: str | None = None) -> dict[str, object]:
    """Return copied text and the matching glyph bounds in rendered-page coordinates."""
    document = pdfium.PdfDocument(str(source), password=password)
    try:
        if not 0 <= page_index < len(document):
            raise ValueError("Invalid text selection page index")
        page = document[page_index]
        try:
            left, bottom, right, top = page.get_bbox()
            rotation = page.get_rotation()
            width, height = right - left, top - bottom

            def canvas(position):
                if len(position) != 2:
                    raise ValueError("Invalid text selection position")
                x, y = (min(1, max(0, float(value))) for value in position)
                if rotation == 90:
                    return left + y * width, bottom + x * height
                if rotation == 180:
                    return right - x * width, bottom + y * height
                if rotation == 270:
                    return right - y * width, top - x * height
                return left + x * width, top - y * height

            def normalized(x, y):
                if rotation == 90:
                    return (y - bottom) / height, (x - left) / width
                if rotation == 180:
                    return (right - x) / width, (y - bottom) / height
                if rotation == 270:
                    return (top - y) / height, (right - x) / width
                return (x - left) / width, (top - y) / height

            x1, y1 = canvas(start)
            x2, y2 = canvas(end)
            textpage = page.get_textpage()
            try:
                first = textpage.get_index(x1, y1, 8, 8)
                last = textpage.get_index(x2, y2, 8, 8)
                if first is not None and last is not None:
                    lo, hi = sorted((first, last))
                    text = textpage.get_text_range(lo, hi - lo + 1)
                else:
                    # Include glyph height around a thin or rotated drag.
                    bounds = (min(x1, x2) - 8, min(y1, y2) - 18,
                              max(x1, x2) + 8, max(y1, y2) + 18)
                    hits = []
                    for index in range(textpage.count_chars()):
                        box = textpage.get_charbox(index)
                        if box and box[0] <= bounds[2] and box[2] >= bounds[0] and box[1] <= bounds[3] and box[3] >= bounds[1]:
                            hits.append(index)
                    if not hits:
                        return {"text": "", "rects": []}
                    lo, hi = hits[0], hits[-1]
                    text = textpage.get_text_range(lo, hi - lo + 1)

                rects = []
                if text:
                    for index in range(lo, hi + 1):
                        box = textpage.get_charbox(index)
                        if not box or box[2] <= box[0] or box[3] <= box[1]:
                            continue
                        corners = [normalized(x, y) for x in (box[0], box[2])
                                   for y in (box[1], box[3])]
                        xs, ys = zip(*corners)
                        rects.append([min(xs), min(ys), max(xs), max(ys)])
                result = {"text": text, "rects": rects}
                if allow_ocr and text and suspicious_text(text):
                    if on_ocr is not None:
                        on_ocr()
                    try:
                        result['text'] = recognize_selection(page, rects)
                        result['ocr_used'] = True
                    except OcrError as exc:
                        result['ocr_error'] = str(exc)
                return result
            finally:
                textpage.close()
        finally:
            page.close()
    finally:
        document.close()


def extract_selection(source: Path, page_index: int, start: list[float], end: list[float]) -> str:
    return str(extract_selection_result(source, page_index, start, end)["text"])


def serve(
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    token: str | None = None,
) -> int:
    input_stream = input_stream if input_stream is not None else sys.stdin
    output_stream = output_stream if output_stream is not None else sys.stdout
    ready = {"type": "ready"}
    if token is not None:
        ready["token"] = token
    print(json.dumps(ready), file=output_stream, flush=True)
    with PdfDocumentCache() as documents:
        for line in input_stream:
            request: dict[str, object] = {}
            try:
                request = json.loads(line)
                if request.get('type') == 'release_document':
                    documents.release(request['source'])
                elif request.get('type') in ('bookmarks', 'navigate'):
                    document = documents.get(request['source'], request.get('password'))
                    result = ({'bookmarks': read_bookmarks(document)} if request['type'] == 'bookmarks'
                              else resolve_destination(document, request['destination']))
                    print(json.dumps({'type': request['type'], 'generation': request['generation'], **result}),
                          file=output_stream, flush=True)
                elif request.get('type') == 'search':
                    from repdf.search import search_document
                    search_document(request, lambda message: print(json.dumps(message), file=output_stream, flush=True))
                elif request.get('type') == 'extract_image':
                    generation = int(request['generation'])
                    destination = Path(request['output_dir']) / f"g{generation}-image.png"
                    result = extract_clicked_image(Path(request['source']), int(request['page']),
                                                   request['point'], destination, password=request.get('password'))
                    print(json.dumps({'type': 'image', 'generation': generation, 'image': result}),
                          file=output_stream, flush=True)
                elif request.get('type') == 'ocr_region':
                    document = pdfium.PdfDocument(str(request['source']), password=request.get('password'))
                    try:
                        page_index = int(request['page'])
                        if not 0 <= page_index < len(document):
                            raise ValueError('Invalid OCR page index')
                        page = document[page_index]
                        try:
                            extracted = recognize_region(page, request['start'], request['end'])
                        finally:
                            page.close()
                    finally:
                        document.close()
                    print(json.dumps({'type': 'text', 'generation': int(request['generation']),
                                      **extracted}), file=output_stream, flush=True)
                elif request.get("type") == "copy_text":
                    extracted = extract_selection_result(Path(request["source"]), int(request["page"]),
                        request["start"], request["end"], allow_ocr=bool(request.get('allow_ocr', False)),
                        password=request.get('password'),
                        on_ocr=lambda: print(json.dumps({'type': 'ocr', 'generation': int(request['generation'])}),
                                             file=output_stream, flush=True))
                    print(json.dumps({"type": "text", "generation": int(request["generation"]),
                                      **extracted}), file=output_stream, flush=True)
                else:
                    render_document(
                        Path(request["source"]), float(request["scale"]),
                        Path(request["output_dir"]), int(request["generation"]), output_stream,
                        pages=request.get("pages"),
                        password=request.get('password'),
                        document=documents.get(request['source'], request.get('password')),
                    )
                print(json.dumps({
                    "type": "done", "generation": int(request["generation"]),
                    "document_id": request.get('document_id'),
                }), file=output_stream, flush=True)
            except Exception as exc:
                print(json.dumps({
                    "type": "error",
                    "generation": request.get("generation", -1) if isinstance(request, dict) else -1,
                    "message": str(exc),
                    "document_id": request.get('document_id') if isinstance(request, dict) else None,
                    "timeout": isinstance(exc, TimeoutError),
                }), file=output_stream, flush=True)
            finally:
                # Release credential references before waiting for the next request.
                if isinstance(request, dict):
                    request.pop('password', None)
                line = ''
    return 0


def serve_socket(port: int, token: str) -> int:
    with socket.create_connection(("127.0.0.1", port), timeout=30) as connection:
        connection.settimeout(None)
        with connection.makefile("r", encoding="utf-8") as reader:
            with connection.makefile("w", encoding="utf-8") as writer:
                return serve(reader, writer, token)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--server":
        return serve()
    if len(sys.argv) != 5:
        print("invalid render worker arguments", file=sys.stderr)
        return 2
    try:
        render_document(
            Path(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
        )
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
