"""PDF-space geometry for editable notes and drawing annotations."""

from copy import deepcopy
from uuid import uuid4

MARKUPS = {"underline", "strikeout", "squiggly", "highlight"}
TEXT_TOOLS = {"callout", "note"}
DRAWINGS = {"line", "arrow", "rectangle", "ellipse", "ink"}


def category(kind):
    return "draw" if kind in DRAWINGS else "text" if kind in TEXT_TOOLS else "mark"


def rect_for(model):
    if model["kind"] in ("line", "arrow"):
        values = model["points"]
    elif model["kind"] == "ink":
        values = [v for path in model["paths"] for v in path]
    else:
        return list(model["rect"])
    xs, ys = values[::2], values[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def translate(model, dx, dy):
    result = deepcopy(model)
    kind = model["kind"]
    if kind in ("line", "arrow"):
        result["points"] = [
            v + (dx if i % 2 == 0 else dy) for i, v in enumerate(model["points"])
        ]
    elif kind == "ink":
        result["paths"] = [
            [v + (dx if i % 2 == 0 else dy) for i, v in enumerate(path)]
            for path in model["paths"]
        ]
    else:
        l, b, r, t = model["rect"]
        result["rect"] = [l + dx, b + dy, r + dx, t + dy]
    return result


def resize(model, rectangle):
    result = deepcopy(model)
    if model["kind"] == "ink":
        l, b, r, t = rect_for(model)
        nl, nb, nr, nt = rectangle
        result["paths"] = [
            [
                nl + (v - l) * (nr - nl) / max(0.01, r - l)
                if i % 2 == 0
                else nb + (v - b) * (nt - nb) / max(0.01, t - b)
                for i, v in enumerate(path)
            ]
            for path in model["paths"]
        ]
    else:
        result["rect"] = list(rectangle)
    return result


def new_drawing(style, page, geometry, start, end):
    model = {
        **deepcopy(style),
        "id": "repdf-" + uuid4().hex,
        "page": page,
        "geometry": deepcopy(geometry),
        "text": "",
    }
    if model["kind"] in ("line", "arrow"):
        model["points"] = [*start, *end]
    elif model["kind"] == "ink":
        model["paths"] = [[*start, *end]]
    else:
        model["rect"] = [
            min(start[0], end[0]),
            min(start[1], end[1]),
            max(start[0], end[0]),
            max(start[1], end[1]),
        ]
    return model
