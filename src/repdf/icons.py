"""Small, flat toolbar icons drawn at device-independent coordinates."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication


def toolbar_icon(kind: str) -> QIcon:
    crop_badge = kind in ('export_trim', 'split_trim')
    if crop_badge:
        kind = kind.removesuffix('_trim')
    icon = QIcon()
    for mode, group, state, role in (
            (QIcon.Mode.Normal, QPalette.ColorGroup.Active, QIcon.State.Off, QPalette.ColorRole.ButtonText),
            (QIcon.Mode.Normal, QPalette.ColorGroup.Active, QIcon.State.On, QPalette.ColorRole.Highlight),
            (QIcon.Mode.Selected, QPalette.ColorGroup.Active, QIcon.State.Off, QPalette.ColorRole.HighlightedText),
            (QIcon.Mode.Selected, QPalette.ColorGroup.Active, QIcon.State.On, QPalette.ColorRole.HighlightedText),
            (QIcon.Mode.Disabled, QPalette.ColorGroup.Disabled, QIcon.State.Off, QPalette.ColorRole.ButtonText),
            (QIcon.Mode.Disabled, QPalette.ColorGroup.Disabled, QIcon.State.On, QPalette.ColorRole.ButtonText)):
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(2, 2)
        painter.setPen(QPen(QApplication.palette().color(group, role),
                            1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        if kind == 'drag_handle':
            painter.setBrush(painter.pen().color())
            for x in (9,15):
                for y in (6,12,18): painter.drawEllipse(QRectF(x-0.75,y-0.75,1.5,1.5))
        elif kind == 'edit_tools':
            painter.drawPolygon(QPolygonF([QPointF(3,21),QPointF(5,15),QPointF(16,4),QPointF(20,8),QPointF(9,19)]))
            painter.drawLine(13,7,17,11)
        elif kind in ('copy', 'select_all_text'):
            if kind == 'copy':
                painter.drawRect(QRectF(8,7,12,14))
                painter.drawPolyline(QPolygonF([QPointF(5,17),QPointF(3,17),QPointF(3,3),QPointF(15,3),QPointF(15,5)]))
            else:
                for x, y, dx, dy in [(3,3,1,1),(21,3,-1,1),(3,21,1,-1),(21,21,-1,-1)]:
                    painter.drawLine(x,y,x+dx*4,y)
                    painter.drawLine(x,y,x,y+dy*4)
                painter.drawLine(7,9,17,9); painter.drawLine(7,15,17,15)
        elif kind in ('note', 'text_box', 'line', 'arrow', 'rectangle', 'ellipse', 'polygon', 'polyline', 'ink', 'stamp', 'attachment', 'caret', 'redact'):
            if kind == 'note':
                painter.drawPolygon(QPolygonF([QPointF(4,3),QPointF(20,3),QPointF(20,15),QPointF(14,21),QPointF(4,21)]))
                painter.drawPolyline(QPolygonF([QPointF(14,21),QPointF(14,15),QPointF(20,15)]))
                painter.drawLine(7,8,17,8); painter.drawLine(7,12,13,12)
            elif kind in ('rectangle', 'text_box', 'redact'):
                painter.drawRoundedRect(QRectF(3,5,18,14),2,2)
                if kind == 'text_box':
                    painter.drawLine(7,9,17,9); painter.drawLine(7,14,14,14)
                elif kind == 'redact':
                    painter.drawLine(4,6,20,18); painter.drawLine(4,18,20,6)
            elif kind == 'ellipse': painter.drawEllipse(QRectF(3,5,18,14))
            elif kind in ('line', 'arrow'):
                painter.drawLine(4,20,20,4)
                if kind == 'arrow':
                    painter.drawLine(20,4,15,4); painter.drawLine(20,4,20,9)
            elif kind in ('polygon','polyline','ink'):
                points=QPolygonF([QPointF(3,17),QPointF(8,5),QPointF(14,18),QPointF(21,8)])
                if kind == 'polygon': painter.drawPolygon(points)
                else: painter.drawPolyline(points)
            elif kind == 'stamp':
                painter.drawRect(QRectF(3,16,18,5))
                painter.drawRoundedRect(QRectF(8,3,8,13),3,3)
            elif kind == 'caret': painter.drawPolyline(QPolygonF([QPointF(5,17),QPointF(12,6),QPointF(19,17)]))
            else:
                path=QPainterPath(QPointF(9,17)); path.lineTo(17,9)
                path.cubicTo(22,4,16,0,12,4); path.lineTo(4,12)
                path.cubicTo(-1,18,7,25,12,20); path.lineTo(20,12)
                painter.drawPath(path)
        elif kind.startswith('annotation_'):
            if kind == 'annotation_callout':
                painter.drawRect(QRectF(8,3,14,10))
                painter.drawLine(11,13,3,21)
                painter.drawLine(3,21,3,16); painter.drawLine(3,21,8,21)
                painter.drawLine(11,6,19,6); painter.drawLine(11,10,17,10)
            else:
                font=QFont(QApplication.font()); font.setPixelSize(16); painter.setFont(font)
                painter.drawText(QRectF(3,1,18,20),Qt.AlignmentFlag.AlignCenter,'A')
                if kind=='annotation_highlight':
                    color = painter.pen().color()
                    color.setAlphaF(.3)
                    painter.fillRect(QRectF(3,4,18,17),color)
                    painter.drawLine(4,21,20,21)
                elif kind=='annotation_strikeout': painter.drawLine(4,12,20,12)
                elif kind=='annotation_squiggly':
                    path=QPainterPath(QPointF(4,21))
                    for i in range(1,9): path.lineTo(4+i*2,20 if i%2 else 22)
                    painter.drawPath(path)
                else: painter.drawLine(4,21,20,21)
        elif kind == 'annotations':
            painter.drawPolyline(QPolygonF([QPointF(4, 3), QPointF(21, 3), QPointF(21, 17),
                                            QPointF(11, 17), QPointF(6, 21), QPointF(6, 17),
                                            QPointF(4, 17), QPointF(4, 3)]))
            painter.drawLine(8, 8, 17, 8)
            painter.drawLine(8, 12, 15, 12)
        elif kind in ('chevron_down', 'chevron_up'):
            pen = painter.pen()
            pen.setWidthF(2)
            painter.setPen(pen)
            points = [(6,9),(12,15),(18,9)] if kind == 'chevron_down' else [(6,15),(12,9),(18,15)]
            painter.drawPolyline(QPolygonF([QPointF(x,y) for x,y in points]))
        elif kind == "more":
            painter.setBrush(painter.pen().color())
            for x in (5, 12, 19):
                painter.drawEllipse(QRectF(x - 1, 11, 2, 2))
        elif kind in ("language_zh", "language_en"):
            font = QFont(QApplication.font())
            font.setPixelSize(16)
            painter.setFont(font)
            painter.drawText(QRectF(1, 1, 22, 22), Qt.AlignmentFlag.AlignCenter,
                             "中" if kind == "language_zh" else "En")
        elif kind == "language_system":
            painter.drawEllipse(QRectF(3, 3, 18, 18))
            painter.drawEllipse(QRectF(8, 3, 8, 18))
            painter.drawLine(3, 12, 21, 12)
        elif kind == "theme_system":
            circle = QPainterPath()
            circle.addEllipse(QRectF(3, 3, 18, 18))
            painter.fillPath(circle, Qt.GlobalColor.white)
            painter.save()
            painter.setClipPath(circle)
            painter.fillRect(QRectF(12, 3, 9, 18), Qt.GlobalColor.black)
            painter.restore()
            painter.drawPath(circle)
        elif kind == "theme_light":
            painter.drawEllipse(QRectF(7, 7, 10, 10))
            for x1, y1, x2, y2 in ((12, 2, 12, 4), (12, 20, 12, 22), (2, 12, 4, 12),
                                    (20, 12, 22, 12), (5, 5, 6, 6), (18, 18, 19, 19),
                                    (5, 19, 6, 18), (18, 6, 19, 5)):
                painter.drawLine(x1, y1, x2, y2)
        elif kind == "theme_dark":
            path = QPainterPath(QPointF(11, 3))
            path.cubicTo(1, 4, 1, 19, 12, 21)
            path.cubicTo(17, 22, 21, 18, 21, 14)
            path.cubicTo(10, 18, 6, 9, 11, 3)
            painter.drawPath(path)
        elif kind == "fit":
            for points in (((3, 8), (3, 3), (8, 3)), ((16, 3), (21, 3), (21, 8)),
                           ((21, 16), (21, 21), (16, 21)), ((8, 21), (3, 21), (3, 16))):
                painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))
            painter.drawRect(QRectF(8, 6, 8, 12))
        elif kind == "trim_view":
            painter.drawPolyline(QPolygonF([QPointF(6, 2), QPointF(6, 18), QPointF(22, 18)]))
            painter.drawPolyline(QPolygonF([QPointF(2, 6), QPointF(18, 6), QPointF(18, 22)]))
        elif kind == "whole_word":
            font = QFont(QApplication.font())
            font.setPixelSize(14)
            painter.setFont(font)
            painter.drawText(QRectF(2, 1, 20, 18), Qt.AlignmentFlag.AlignCenter, 'ab')
            painter.drawPolyline(QPolygonF([QPointF(3, 18), QPointF(3, 21),
                                            QPointF(21, 21), QPointF(21, 18)]))
        elif kind in ("regex", "case_sensitive"):
            font = QFont(QApplication.font())
            font.setPixelSize(17 if kind == "regex" else 15)
            painter.setFont(font)
            painter.drawText(QRectF(1, 1, 22, 22), Qt.AlignmentFlag.AlignCenter,
                             ".*" if kind == "regex" else "Aa")
        elif kind == "close":
            painter.drawLine(6, 6, 18, 18)
            painter.drawLine(18, 6, 6, 18)
        elif kind == "stop":
            painter.setBrush(painter.pen().color())
            painter.drawRect(QRectF(6, 6, 12, 12))
        elif kind in ("previous", "next"):
            x1, x2 = (15, 8) if kind == 'previous' else (9, 16)
            painter.drawPolyline(QPolygonF([QPointF(x1, 5), QPointF(x2, 12), QPointF(x1, 19)]))
        elif kind == "print":
            painter.drawRect(QRectF(6, 2, 12, 6))
            painter.drawPolyline(QPolygonF([QPointF(6, 17), QPointF(3, 17), QPointF(3, 8),
                                            QPointF(21, 8), QPointF(21, 17), QPointF(18, 17)]))
            painter.drawRect(QRectF(6, 13, 12, 9))
            painter.drawLine(16, 10, 18, 10)
            painter.drawLine(9, 16, 15, 16)
            painter.drawLine(9, 19, 15, 19)
        elif kind == "bookmarks":
            painter.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(18, 3), QPointF(18, 21),
                                            QPointF(12, 17), QPointF(6, 21)]))
        elif kind == "search":
            painter.drawEllipse(QRectF(3, 3, 13, 13))
            painter.drawLine(14, 14, 21, 21)
        elif kind == "extract_image":
            painter.drawRect(QRectF(3, 3, 18, 14))
            painter.drawEllipse(QRectF(6, 6, 3, 3))
            painter.drawPolyline(QPolygonF([QPointF(4, 16), QPointF(10, 10), QPointF(14, 14), QPointF(17, 11), QPointF(20, 14)]))
            painter.drawLine(12, 17, 12, 22)
            painter.drawLine(9, 19, 12, 22)
            painter.drawLine(15, 19, 12, 22)
        elif kind == "ocr_region":
            for points in (((3, 8), (3, 3), (8, 3)), ((16, 3), (21, 3), (21, 8)),
                           ((21, 16), (21, 21), (16, 21)), ((8, 21), (3, 21), (3, 16))):
                painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))
            font = QFont(QApplication.font())
            font.setPixelSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(5, 4, 14, 16), Qt.AlignmentFlag.AlignCenter, 'A')
        elif kind == "copy_text":
            painter.drawLine(3, 4, 18, 4)
            painter.drawLine(3, 8, 16, 8)
            painter.drawLine(3, 12, 13, 12)
            painter.drawLine(3, 16, 10, 16)
            painter.drawLine(17, 11, 17, 21)
            painter.drawLine(14, 11, 20, 11)
            painter.drawLine(14, 21, 20, 21)
        elif kind in ("fullscreen", "fullscreen_spread", "fullscreen_cover"):
            if kind == "fullscreen":
                painter.drawRect(QRectF(5, 2, 14, 20))
                painter.drawLine(8, 11, 16, 11)
                painter.drawLine(8, 15, 16, 15)
            elif kind == "fullscreen_spread":
                painter.drawRect(QRectF(3, 4, 18, 17))
                painter.drawLine(12, 4, 12, 21)
                painter.drawLine(5, 12, 9, 12)
                painter.drawLine(15, 12, 19, 12)
            else:
                painter.drawRect(QRectF(1, 2, 10, 19))
                painter.drawLine(4, 11, 8, 11)
                # A separate cover beside two pages sharing their center edge.
                painter.drawRect(QRectF(13, 8, 10, 13))
                painter.drawLine(18, 8, 18, 21)
        elif kind == "open":
            painter.drawPolyline(QPolygonF([QPointF(3, 19), QPointF(3, 5), QPointF(9, 5),
                                            QPointF(12, 8), QPointF(20, 8), QPointF(20, 10)]))
            painter.drawPolygon(QPolygonF([QPointF(3, 19), QPointF(7, 11), QPointF(22, 11),
                                           QPointF(18, 19)]))
        elif kind == 'save_as':
            # Two overlapping disks distinguish Save As from Save at toolbar size.
            painter.drawRect(QRectF(2, 2, 14, 16))
            painter.drawRect(QRectF(5, 2, 8, 5))
            painter.drawRect(QRectF(5, 12, 8, 6))
            painter.fillRect(QRectF(7, 6, 2, 2), painter.pen().color())
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(QRectF(8, 8, 15, 15), Qt.GlobalColor.transparent)
            painter.restore()
            painter.drawRect(QRectF(8, 8, 14, 14))
            painter.drawRect(QRectF(11, 8, 8, 5))
            painter.drawRect(QRectF(11, 16, 8, 6))
        elif kind == 'save':
            painter.drawPolyline(QPolygonF([QPointF(3, 3), QPointF(17, 3), QPointF(21, 7),
                                            QPointF(21, 21), QPointF(3, 21), QPointF(3, 3)]))
            painter.drawRect(QRectF(7, 3, 9, 6))
            painter.drawRect(QRectF(7, 14, 10, 7))
        elif kind == "export":
            painter.drawPolygon(QPolygonF([QPointF(4, 2), QPointF(14, 2), QPointF(20, 8),
                                           QPointF(20, 22), QPointF(4, 22)]))
            painter.drawPolyline(QPolygonF([QPointF(14, 2), QPointF(14, 8), QPointF(20, 8)]))
            painter.drawLine(12, 11, 12, 18)
            painter.drawPolyline(QPolygonF([QPointF(8, 14), QPointF(12, 18), QPointF(16, 14)]))
        elif kind == "split":
            painter.drawRoundedRect(QRectF(2, 2, 8, 13), 1, 1)
            painter.drawRoundedRect(QRectF(14, 9, 8, 13), 1, 1)
            painter.drawLine(6, 19, 12, 19)
            painter.drawPolyline(QPolygonF([QPointF(9, 16), QPointF(12, 19), QPointF(9, 22)]))
        elif kind in ("zoom_in", "zoom_out"):
            painter.drawEllipse(QRectF(3, 3, 13, 13))
            painter.drawLine(15, 15, 21, 21)
            painter.drawLine(6, 9, 13, 9)
            if kind == "zoom_in":
                painter.drawLine(9, 6, 9, 13)
        if crop_badge:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(QRectF(13, 0, 11, 12), Qt.GlobalColor.transparent)
            painter.restore()
            painter.drawPolyline(QPolygonF([QPointF(16, 1), QPointF(16, 8), QPointF(23, 8)]))
            painter.drawPolyline(QPolygonF([QPointF(13, 4), QPointF(20, 4), QPointF(20, 11)]))
        painter.end()
        icon.addPixmap(pixmap, mode, state)
        if mode == QIcon.Mode.Normal:
            icon.addPixmap(pixmap, QIcon.Mode.Active, state)
    return icon


def annotation_icon(kind: str) -> QIcon:
    names = {
        '備註': 'note', '文字方塊': 'text_box', '直線': 'line', '箭頭': 'arrow',
        '矩形': 'rectangle', '橢圓': 'ellipse', '多邊形': 'polygon',
        '折線': 'polyline', '手繪': 'ink', '印章': 'stamp',
        '附件': 'attachment', '插入符號': 'caret', '遮蔽標記': 'redact',
        '螢光標示': 'annotation_highlight', '螢光筆': 'annotation_highlight',
        '底線': 'annotation_underline', '刪除線': 'annotation_strikeout',
        '波浪底線': 'annotation_squiggly',
    }
    return toolbar_icon(names.get(kind, 'annotations'))
