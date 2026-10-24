"""Shared vector painting for interactive overlays and embedded PDF appearances."""

import base64
import math
from copy import deepcopy

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPageLayout,
    QPageSize,
    QPainter,
    QPainterPath,
    QPdfWriter,
    QPen,
    QPolygonF,
    QTextDocument,
    QTransform,
)

from repdf.annotation_data import bounds
from repdf.annotation_geometry import DRAWINGS, translate


def transform(geometry, width, height):
    l, b, r, t = geometry["box"]
    w, h = r - l, t - b
    rotation = geometry["rotation"]
    if rotation == 90:
        return QTransform(0, height / w, width / h, 0, -b * width / h, -l * height / w)
    if rotation == 180:
        return QTransform(-width / w, 0, 0, height / h, r * width / w, -b * height / h)
    if rotation == 270:
        return QTransform(0, -height / w, -width / h, 0, t * width / h, r * height / w)
    return QTransform(width / w, 0, 0, -height / h, -l * width / w, t * height / h)


def paint(painter, model, *, editing=False):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(model["color"]))
    pen.setWidthF(model["width"])
    painter.setPen(pen)
    if model["kind"] in DRAWINGS or model["kind"] == "note":
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        kind = model["kind"]
        if kind == "note":
            l, b, r, t = model["rect"]
            inset = min(model["width"] / 2, (r - l) / 4, (t - b) / 4)
            l, b, r, t = l + inset, b + inset, r - inset, t - inset
            fold = min(6, (r - l) / 3, (t - b) / 3)
            path = QPainterPath(QPointF(l, b))
            for point in [(r, b), (r, t - fold), (r - fold, t), (l, t), (l, b)]:
                path.lineTo(*point)
            painter.fillPath(path, QColor(model["color"]).lighter(180))
            painter.drawPath(path)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(r - fold, t),
                        QPointF(r - fold, t - fold),
                        QPointF(r, t - fold),
                    ]
                )
            )
            painter.drawLine(QPointF(l + 4, t - 9), QPointF(r - 8, t - 9))
            painter.drawLine(QPointF(l + 4, t - 14), QPointF(r - 5, t - 14))
        elif kind in ("rectangle", "ellipse"):
            l, b, r, t = model["rect"]
            rect = QRectF(l, b, r - l, t - b)
            painter.setBrush(
                QColor(model["background"])
                if model.get("background")
                else Qt.BrushStyle.NoBrush
            )
            if kind == "ellipse":
                painter.drawEllipse(rect)
            else:
                painter.drawRect(rect)
        else:
            paths = model["paths"] if kind == "ink" else [model["points"]]
            for values in paths:
                path = QPainterPath(QPointF(*values[:2]))
                for i in range(2, len(values), 2):
                    path.lineTo(values[i], values[i + 1])
                painter.drawPath(path)
            if kind == "arrow":
                x, y, ex, ey = model["points"]
                length = max(0.01, math.hypot(ex - x, ey - y))
                ux, uy = (ex - x) / length, (ey - y) / length
                size = max(6, model["width"] * 4)
                path = QPainterPath(
                    QPointF(
                        ex - ux * size - uy * size * 0.45,
                        ey - uy * size + ux * size * 0.45,
                    )
                )
                path.lineTo(ex, ey)
                path.lineTo(
                    ex - ux * size + uy * size * 0.45, ey - uy * size - ux * size * 0.45
                )
                painter.drawPath(path)
        painter.restore()
        return
    if model["kind"] != "callout":
        for q in model["quads"]:
            if model["kind"] == "highlight":
                color = QColor(model["color"])
                color.setAlphaF(0.35)
                path = QPainterPath(QPointF(q[0], q[1]))
                for i in (2, 6, 4):
                    path.lineTo(q[i], q[i + 1])
                path.closeSubpath()
                painter.fillPath(path, color)
                continue
            a, b = QPointF(q[4], q[5]), QPointF(q[6], q[7])
            if model["kind"] == "strikeout":
                a = (a + QPointF(q[0], q[1])) / 2
                b = (b + QPointF(q[2], q[3])) / 2
            if model["kind"] == "squiggly":
                dx, dy = b.x() - a.x(), b.y() - a.y()
                length = math.hypot(dx, dy)
                steps = max(2, math.ceil(length / max(1, model["width"] * 2)))
                path = QPainterPath(a)
                for i in range(1, steps + 1):
                    height = (
                        (model["width"] if i % 2 else -model["width"])
                        if i < steps
                        else 0
                    )
                    path.lineTo(
                        a.x() + dx * i / steps - dy / max(length, 1) * height,
                        a.y() + dy * i / steps + dx / max(length, 1) * height,
                    )
                painter.drawPath(path)
            else:
                painter.drawLine(a, b)
    else:
        l, b, r, t = model["rect"]
        rect = QRectF(l, b, r - l, t - b)
        if not editing:
            radius = min(model.get("radius", 0), rect.width() / 2, rect.height() / 2)
            frame = QPainterPath()
            frame.addRoundedRect(rect, radius, radius)
            if model.get("background"):
                painter.fillPath(frame, QColor(model["background"]))
            painter.drawPath(frame)
        points = [
            QPointF(*model["leader"][i : i + 2])
            for i in range(0, len(model["leader"]), 2)
        ]
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.drawPath(path)
        a, bp = points[:2]
        dx, dy = bp.x() - a.x(), bp.y() - a.y()
        length = max(1, math.hypot(dx, dy))
        ux, uy = dx / length, dy / length
        size = max(5, model["width"] * 4)
        left = QPointF(
            a.x() + ux * size - uy * size * 0.45, a.y() + uy * size + ux * size * 0.45
        )
        right = QPointF(
            a.x() + ux * size + uy * size * 0.45, a.y() + uy * size - ux * size * 0.45
        )
        arrow = QPainterPath(left)
        arrow.lineTo(a)
        arrow.lineTo(right)
        if model.get("ending") == "ClosedArrow":
            arrow.closeSubpath()
            painter.fillPath(arrow, QColor(model["color"]))
        painter.drawPath(arrow)
        if editing:
            painter.restore()
            return
        rotation = model.get("text_rotation", 0)
        origins = {0: (l, t), 90: (l, b), 180: (r, b), 270: (r, t)}
        painter.translate(*origins[rotation])
        painter.rotate(rotation)
        painter.scale(1, -1)
        text_width, text_height = (
            (t - b, r - l) if rotation in (90, 270) else (r - l, t - b)
        )
        painter.setClipRect(
            QRectF(1, 1, max(1, text_width - 2), max(1, text_height - 2))
        )
        doc = QTextDocument()
        font = QFont(model.get("font", "Arial"))
        font.setPixelSize(round(model["size"]))
        doc.setDefaultFont(font)
        doc.setDocumentMargin(4)
        doc.setPlainText(model["text"])
        doc.setTextWidth(text_width)
        from PySide6.QtGui import QAbstractTextDocumentLayout, QPalette

        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(QPalette.ColorRole.Text, QColor(model["text_color"]))
        doc.documentLayout().draw(painter, context)
    painter.restore()


def appearance(model):
    box = bounds(model)
    width, height = box[2] - box[0], box[3] - box[1]
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QPdfWriter(buffer)
    writer.setResolution(72)
    writer.setPageSize(QPageSize(QSizeF(width, height), QPageSize.Unit.Point))
    from PySide6.QtCore import QMarginsF

    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
    painter = QPainter(writer)
    painter.translate(-box[0], box[3])
    painter.scale(1, -1)
    paint(painter, model)
    painter.end()
    del writer
    buffer.close()
    return base64.b64encode(bytes(data)).decode("ascii")


def moved(model, dx, dy):
    if model["kind"] in DRAWINGS or model["kind"] == "note":
        return translate(model, dx, dy)
    m = deepcopy(model)
    if m["kind"] == "callout":
        l, b, r, t = m["rect"]
        m["rect"] = [l + dx, b + dy, r + dx, t + dy]
        for i in range(2, len(m["leader"]), 2):
            m["leader"][i] += dx
            m["leader"][i + 1] += dy
    return m


def reroute(model):
    m = deepcopy(model)
    l, b, r, t = m["rect"]
    x, y = m["leader"][:2]
    candidates = [
        (abs(x - l), [l, max(b, min(t, y))], [-16, 0]),
        (abs(x - r), [r, max(b, min(t, y))], [16, 0]),
        (abs(y - b), [max(l, min(r, x)), b], [0, -16]),
        (abs(y - t), [max(l, min(r, x)), t], [0, 16]),
    ]
    _, port, offset = min(
        candidates, key=lambda entry: (entry[1][0] - x) ** 2 + (entry[1][1] - y) ** 2
    )
    if len(m["leader"]) == 4:
        m["leader"] = [x, y, *port]
    else:
        gl, gb, gr, gt = m["geometry"]["box"]
        knee = [
            max(gl, min(gr, port[0] + offset[0])),
            max(gb, min(gt, port[1] + offset[1])),
        ]
        m["leader"] = [x, y, *knee, *port]
    return m


def selection_top_center(quads, geometry):
    """Return the upper midpoint of selected glyphs in upright page space."""
    l, b, r, t = geometry["box"]
    width, height = (
        (t - b, r - l) if geometry["rotation"] in (90, 270) else (r - l, t - b)
    )
    tx = transform(geometry, width, height)
    points = [tx.map(QPointF(q[i], q[i + 1])) for q in quads for i in range(0, 8, 2)]
    midpoint = QPointF(
        (min(p.x() for p in points) + max(p.x() for p in points)) / 2,
        min(p.y() for p in points),
    )
    inverse, _ = tx.inverted()
    return inverse.map(midpoint)
