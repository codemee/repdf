"""Editable PDF annotation data, conservative import, and standard PDF output."""

from __future__ import annotations

import base64
from copy import deepcopy
import io
import hashlib
import json
import math
from uuid import uuid4

from pypdf import PdfReader
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
    DecodedStreamObject,
)

from repdf.annotation_geometry import DRAWINGS, rect_for

KINDS = {
    "Underline": "underline",
    "StrikeOut": "strikeout",
    "Squiggly": "squiggly",
    "Highlight": "highlight",
    "Text": "note",
    "Line": "line",
    "Square": "rectangle",
    "Circle": "ellipse",
    "Ink": "ink",
}
SUBTYPES = {value: key for key, value in KINDS.items()}
SUBTYPES["arrow"] = "Line"


def numbers(values, count=None):
    values = values.get_object() if hasattr(values, "get_object") else values
    result = [float(v) for v in values]
    if (count is not None and len(result) != count) or not all(
        math.isfinite(v) and abs(v) < 1e7 for v in result
    ):
        raise ValueError("Invalid annotation geometry")
    return result


def rgb(values):
    v = numbers(values)
    if len(v) == 1:
        v *= 3
    elif len(v) == 4:
        c, m, y, k = v
        v = [1 - min(1, c + k), 1 - min(1, m + k), 1 - min(1, y + k)]
    if len(v) != 3 or any(not 0 <= x <= 1 for x in v):
        raise ValueError("Unsupported annotation colour")
    return "#" + "".join(f"{round(x * 255):02x}" for x in v)


def colour(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        raise ValueError("Invalid annotation colour")
    return [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]


def validate(model):
    allowed = {
        "id",
        "page",
        "geometry",
        "source_index",
        "kind",
        "text",
        "quads",
        "rect",
        "leader",
        "width",
        "color",
        "text_color",
        "size",
        "background",
        "font",
        "ending",
        "appearance_pdf",
        "text_rotation",
        "radius",
        "points",
        "paths",
    }
    m = {key: deepcopy(value) for key, value in model.items() if key in allowed}
    if m["kind"] not in {*SUBTYPES, "callout"}:
        raise ValueError("Unsupported annotation")
    m["width"] = float(m["width"])
    if not 0.5 <= m["width"] <= 6:
        raise ValueError("Unsupported line width")
    colour(m["color"])
    if m["kind"] in DRAWINGS or m["kind"] == "note":
        if m["kind"] in ("line", "arrow"):
            m["points"] = numbers(m["points"], 4)
            x, y, ex, ey = m["points"]
            if math.hypot(ex - x, ey - y) < 2:
                raise ValueError("Drawing is too small")
        elif m["kind"] == "ink":
            if not isinstance(m["paths"], list) or not 1 <= len(m["paths"]) <= 1000:
                raise ValueError("Invalid ink paths")
            m["paths"] = [numbers(path) for path in m["paths"]]
            if (
                any(len(path) < 4 or len(path) % 2 for path in m["paths"])
                or sum(map(len, m["paths"])) > 20000
            ):
                raise ValueError("Invalid ink paths")
            l, b, r, t = rect_for(m)
            if math.hypot(r - l, t - b) < 2:
                raise ValueError("Drawing is too small")
        else:
            m["rect"] = numbers(m["rect"], 4)
            l, b, r, t = m["rect"]
            if r - l < 2 or t - b < 2:
                raise ValueError("Drawing is too small")
        if m.get("background"):
            colour(m["background"])
        if m["kind"] == "note" and (
            not isinstance(m.get("text"), str)
            or not m["text"].strip()
            or len(m["text"]) > 100000
        ):
            raise ValueError("Invalid annotation text")
    elif m["kind"] == "callout":
        m["radius"] = float(m.get("radius", 0))
        if not math.isfinite(m["radius"]) or not 0 <= m["radius"] <= 24:
            raise ValueError("Invalid corner radius")
        m["rect"] = numbers(m["rect"], 4)
        l, b, r, t = m["rect"]
        if r - l < 8 or t - b < 8:
            raise ValueError("Invalid text box")
        m["leader"] = numbers(m["leader"])
        if len(m["leader"]) not in (4, 6):
            raise ValueError("Unsupported callout leader")
        if m.get("ending", "OpenArrow") not in ("OpenArrow", "ClosedArrow"):
            raise ValueError("Unsupported arrow ending")
        m["text_rotation"] = int(m.get("text_rotation", 0))
        if m["text_rotation"] not in (0, 90, 180, 270):
            raise ValueError("Unsupported text rotation")
        m["size"] = float(m["size"])
        if not 8 <= m["size"] <= 72:
            raise ValueError("Unsupported font size")
        if (
            not isinstance(m["text"], str)
            or not m["text"].strip()
            or len(m["text"]) > 100000
        ):
            raise ValueError("Invalid annotation text")
        colour(m["text_color"])
        if m.get("background"):
            colour(m["background"])
    else:
        m["quads"] = [numbers(q, 8) for q in m["quads"]]
        if not m["quads"]:
            raise ValueError("Missing text geometry")
        for q in m["quads"]:
            if math.hypot(q[4] - q[0], q[5] - q[1]) > math.hypot(
                q[6] - q[0], q[7] - q[1]
            ):
                q[4:8] = q[6:8] + q[4:6]
    return m


def bounds(m):
    if m["kind"] == "note":
        return list(m["rect"])
    if m["kind"] in DRAWINGS:
        l, b, r, t = rect_for(m)
        padding = (
            max(6, m["width"] * 4) if m["kind"] == "arrow" else max(5, m["width"] * 3)
        )
        return [l - padding, b - padding, r + padding, t + padding]
    if m["kind"] == "callout":
        l, b, r, t = m["rect"]
        xs = [l, r, *m["leader"][::2]]
        ys = [b, t, *m["leader"][1::2]]
    else:
        xs = [x for q in m["quads"] for x in q[::2]]
        ys = [y for q in m["quads"] for y in q[1::2]]
    padding = max(5, m["width"] * 3)
    return [min(xs) - padding, min(ys) - padding, max(xs) + padding, max(ys) + padding]


def signature(annotation):
    def canonical(value):
        value = value.get_object() if hasattr(value, "get_object") else value
        if isinstance(value, dict):
            return {
                str(key): canonical(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [canonical(item) for item in value]
        if isinstance(value, (int, float)):
            return float(FloatObject(value).myrepr())
        return str(value) if value is not None else None

    keys = (
        "/Subtype",
        "/Rect",
        "/Contents",
        "/C",
        "/DA",
        "/RD",
        "/CL",
        "/LE",
        "/QuadPoints",
        "/Rotate",
        "/BS",
        "/RC",
    )
    if str(annotation.get("/Subtype")) in (
        "/Text",
        "/Line",
        "/Square",
        "/Circle",
        "/Ink",
    ):
        keys += ("/L", "/InkList", "/IC", "/Name")
    state = {key: canonical(annotation.get(key)) for key in keys}
    normal = annotation["/AP"]["/N"].get_object()
    state["appearance"] = hashlib.sha256(normal.get_data()).hexdigest()
    state["bbox"] = canonical(normal.get("/BBox"))
    state["matrix"] = canonical(normal.get("/Matrix"))
    fonts = (
        normal.get("/Resources", DictionaryObject())
        .get_object()
        .get("/Font", DictionaryObject())
        .get_object()
    )
    state["fonts"] = {
        str(key): str(value.get_object().get("/BaseFont", ""))
        for key, value in fonts.items()
    }
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def read_models(reader, page_index):
    """Import only geometry/styles that our editor can faithfully represent."""
    page = reader.pages[page_index]
    geometry = {
        "box": numbers(page.cropbox, 4),
        "rotation": int(page.get("/Rotate", 0)) % 360,
    }
    models, reasons = [], {}
    for index, ref in enumerate(page.get("/Annots", ArrayObject()).get_object()):
        try:
            a = ref.get_object()
        except Exception:
            reasons[index] = "Annotation data could not be parsed reliably"
            continue
        if not isinstance(a, DictionaryObject):
            reasons[index] = "Annotation data could not be parsed reliably"
            continue
        subtype = str(a.get("/Subtype", "")).lstrip("/")
        if subtype not in (*KINDS, "FreeText"):
            continue
        try:
            flags = int(a.get("/F", 0))
            if flags & (1 | 2 | 32):
                continue
            if flags & (64 | 128 | 512):
                raise ValueError("Annotation is locked or read-only")
            own = bool(a.get("/RepdfData"))
            if own:
                data = str(a["/RepdfData"])
                if len(data) > 1_000_000:
                    raise ValueError("Unsupported annotation data")
                m = json.loads(data)
                expected = m.pop("appearance_signature", None)
                if expected is not None and expected != signature(a):
                    raise ValueError("Annotation editing data is inconsistent")
                if m.get("text", "") != str(a.get("/Contents", "")):
                    raise ValueError("Annotation editing data is inconsistent")
                if m.pop("version", None) != 1:
                    raise ValueError("Unsupported annotation version")
            else:
                if subtype in ("Text", "Line", "Square", "Circle", "Ink"):
                    raise ValueError("Existing note or drawing appearance is read-only")
                if subtype == "FreeText" and "/RC" in a:
                    raise ValueError("Rich text is read-only")
                border = a.get("/BS", DictionaryObject()).get_object()
                if (
                    border.get("/S", "/S") != "/S"
                    or float(a.get("/CA", 1)) != 1
                    or a.get("/BE")
                ):
                    raise ValueError("Unsupported border or transparency effect")
                m = {
                    "kind": KINDS.get(subtype, "callout"),
                    "text": str(a.get("/Contents", "")),
                    "color": rgb(a.get("/C", [0, 0, 0])),
                    "width": float(
                        a.get("/BS", DictionaryObject())
                        .get_object()
                        .get("/W", a.get("/Border", [0, 0, 1])[2])
                    ),
                }
                if subtype == "FreeText":
                    if "/CL" not in a:
                        raise ValueError("Text box has no callout leader")
                    if a.get("/IT", "/FreeTextCallout") != "/FreeTextCallout":
                        raise ValueError("Unsupported text box intent")
                    import re

                    da = str(a.get("/DA", ""))
                    font = re.search(r"/([^\s]+)\s+([\d.]+)\s+Tf", da)
                    if not font or font[1].lower() not in (
                        "helv",
                        "helvetica",
                        "arial",
                        "cour",
                        "courier",
                        "tiro",
                        "times-roman",
                    ):
                        raise ValueError("Font cannot be restored reliably")
                    size = float(font[2])
                    text_colour = re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg", da)
                    text_color = rgb(text_colour.groups()) if text_colour else "#000000"
                    stroke_colour = re.search(
                        r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+RG", da
                    )
                    m["color"] = (
                        rgb(stroke_colour.groups()) if stroke_colour else "#000000"
                    )
                    rect = numbers(a["/Rect"], 4)
                    rd = numbers(a.get("/RD", [0, 0, 0, 0]), 4)
                    m.update(
                        rect=[
                            rect[0] + rd[0],
                            rect[1] + rd[1],
                            rect[2] - rd[2],
                            rect[3] - rd[3],
                        ],
                        leader=numbers(a["/CL"]),
                        size=size,
                        text_rotation=int(a.get("/Rotate", 0)),
                        text_color=text_color,
                        background=rgb(a["/C"]) if "/C" in a else None,
                        ending=str(a.get("/LE", "/OpenArrow")).lstrip("/"),
                        font={
                            "cour": "Courier New",
                            "courier": "Courier New",
                            "tiro": "Times New Roman",
                            "times-roman": "Times New Roman",
                        }.get(font[1].lower(), "Arial"),
                    )
                    # External appearance streams can use colours not expressed
                    # by standard style fields. Keep those callouts read-only.
                    if "/AP" in a:
                        from pypdf.generic import ContentStream

                        ap = a["/AP"].get("/N")
                        if not hasattr(ap.get_object(), "get_data"):
                            raise ValueError("Unsupported appearance states")
                        content = ContentStream(ap, reader)
                        supported = {
                            b"q",
                            b"Q",
                            b"cm",
                            b"RG",
                            b"rg",
                            b"G",
                            b"g",
                            b"K",
                            b"k",
                            b"w",
                            b"J",
                            b"j",
                            b"M",
                            b"d",
                            b"m",
                            b"l",
                            b"c",
                            b"v",
                            b"y",
                            b"h",
                            b"re",
                            b"S",
                            b"s",
                            b"f",
                            b"f*",
                            b"F",
                            b"B",
                            b"B*",
                            b"b",
                            b"b*",
                            b"n",
                            b"W",
                            b"W*",
                            b"BT",
                            b"ET",
                            b"Tf",
                            b"Tm",
                            b"Td",
                            b"TD",
                            b"Tj",
                            b"TJ",
                            b"'",
                            b'"',
                            b"Tc",
                            b"Tw",
                            b"Tz",
                            b"TL",
                            b"Tr",
                            b"Ts",
                        }
                        supported.update((b"gs", b"BMC", b"BDC", b"EMC", b"MP", b"DP"))
                        resources = (
                            ap.get_object()
                            .get("/Resources", DictionaryObject())
                            .get_object()
                        )
                        for operands, operator in content.operations:
                            if operator not in supported:
                                raise ValueError("Unsupported custom appearance effect")
                            if operator == b"gs":
                                states = resources.get(
                                    "/ExtGState", DictionaryObject()
                                ).get_object()
                                state = states.get(
                                    operands[0], DictionaryObject()
                                ).get_object()
                                if (
                                    float(state.get("/CA", 1)) != 1
                                    or float(state.get("/ca", 1)) != 1
                                    or state.get("/BM", "/Normal")
                                    not in ("/Normal", "/Compatible")
                                    or state.get("/SMask", "/None") != "/None"
                                    or "/TR" in state
                                    or "/TR2" in state
                                ):
                                    raise ValueError(
                                        "Unsupported border or transparency effect"
                                    )
                            if operator == b"RG":
                                m["color"] = rgb(operands)
                            elif operator == b"G":
                                m["color"] = rgb(operands)
                            elif operator == b"K":
                                m["color"] = rgb(operands)
                            elif operator == b"w":
                                m["width"] = float(operands[0])
                        # Uniform standard-font appearances can be recreated.
                        fonts = resources.get("/Font", DictionaryObject()).get_object()
                        used_fonts = {
                            operands[0]
                            for operands, operator in content.operations
                            if operator == b"Tf"
                        }
                        if len(used_fonts) != 1 or any(
                            name not in fonts for name in used_fonts
                        ):
                            raise ValueError("Embedded or custom font is read-only")
                        aliases = {
                            "Helvetica": "Arial",
                            "Arial": "Arial",
                            "ArialMT": "Arial",
                            "Courier": "Courier New",
                            "CourierNewPSMT": "Courier New",
                            "Times-Roman": "Times New Roman",
                            "TimesNewRomanPSMT": "Times New Roman",
                        }
                        for font_key in used_fonts:
                            resource = fonts[font_key]
                            name = str(
                                resource.get_object().get("/BaseFont", "")
                            ).lstrip("/")
                            name = re.sub(r"^[A-Z]{6}\+", "", name)
                            if name not in aliases:
                                raise ValueError("Embedded or custom font is read-only")
                            m["font"] = aliases[name]

                else:
                    points = numbers(a.get("/QuadPoints", []))
                    if not points or len(points) % 8:
                        raise ValueError("Missing text quadrilaterals")
                    m["quads"] = [points[i : i + 8] for i in range(0, len(points), 8)]
            m.update(
                id=str(a.get("/NM", f"page-{page_index}-annotation-{index}"))
                if own
                else f"page-{page_index}-annotation-{index}",
                page=page_index,
                source_index=index,
                geometry=geometry,
            )
            models.append(validate(m))
        except (
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            AttributeError,
            OverflowError,
        ) as exc:
            reasons[index] = str(exc)
    return models, reasons, geometry


def apply_changes(writer, changes):
    """Apply a frozen delta before page reordering or selected-page export."""
    deleted_indices = set()
    for m in changes:
        page = writer.pages[m["page"]]
        annotations = page.get("/Annots", ArrayObject()).get_object()
        target = None
        index = m.get("source_index")
        if index is not None:
            # Deletions are deferred so source indices remain stable.
            if not 0 <= index < len(annotations):
                raise ValueError("Annotation source has changed")
            target = annotations[index].get_object()
        if m.get("deleted"):
            if target is not None:
                deleted_indices.add((m["page"], index))
            continue
        m = validate(m)
        obj = target if target is not None else DictionaryObject()
        clean = {
            k: v
            for k, v in m.items()
            if k not in ("page", "source_index", "geometry", "appearance_pdf", "id")
        }
        clean["version"] = 1
        obj.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject(
                    "/FreeText" if m["kind"] == "callout" else "/" + SUBTYPES[m["kind"]]
                ),
                NameObject("/NM"): TextStringObject(
                    m["id"] if m["id"].startswith("repdf-") else "repdf-" + uuid4().hex
                ),
                NameObject("/Contents"): TextStringObject(m.get("text", "")),
                NameObject("/F"): NumberObject(4),
                NameObject("/RepdfData"): TextStringObject(
                    json.dumps(clean, ensure_ascii=False)
                ),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in bounds(m)]),
                NameObject("/BS"): DictionaryObject(
                    {
                        NameObject("/W"): FloatObject(m["width"]),
                        NameObject("/S"): NameObject("/S"),
                    }
                ),
            }
        )
        if m["kind"] == "callout":
            obj[NameObject("/Rotate")] = NumberObject(m.get("text_rotation", 0))
            obj[NameObject("/IT")] = NameObject("/FreeTextCallout")
            obj[NameObject("/CL")] = ArrayObject([FloatObject(v) for v in m["leader"]])
            obj[NameObject("/LE")] = NameObject("/" + m.get("ending", "OpenArrow"))
            obj[NameObject("/DA")] = TextStringObject(
                f"/Helv {m['size']} Tf "
                + " ".join(map(str, colour(m["text_color"])))
                + " rg"
            )
            outer = bounds(m)
            inner = m["rect"]
            obj[NameObject("/RD")] = ArrayObject(
                [
                    FloatObject(v)
                    for v in (
                        inner[0] - outer[0],
                        inner[1] - outer[1],
                        outer[2] - inner[2],
                        outer[3] - inner[3],
                    )
                ]
            )
            if m.get("background"):
                obj[NameObject("/C")] = ArrayObject(
                    [FloatObject(v) for v in colour(m["background"])]
                )
            else:
                obj.pop("/C", None)
        elif m["kind"] in DRAWINGS or m["kind"] == "note":
            obj[NameObject("/C")] = ArrayObject(
                [FloatObject(v) for v in colour(m["color"])]
            )
            if m["kind"] == "note":
                obj[NameObject("/Name")] = NameObject("/Comment")
            elif m["kind"] in ("line", "arrow"):
                obj[NameObject("/L")] = ArrayObject(
                    [FloatObject(v) for v in m["points"]]
                )
                obj[NameObject("/LE")] = ArrayObject(
                    [
                        NameObject("/None"),
                        NameObject("/OpenArrow" if m["kind"] == "arrow" else "/None"),
                    ]
                )
            elif m["kind"] == "ink":
                obj[NameObject("/InkList")] = ArrayObject(
                    [ArrayObject([FloatObject(v) for v in path]) for path in m["paths"]]
                )
            else:
                outer, inner = bounds(m), m["rect"]
                obj[NameObject("/RD")] = ArrayObject(
                    [
                        FloatObject(v)
                        for v in (
                            inner[0] - outer[0],
                            inner[1] - outer[1],
                            outer[2] - inner[2],
                            outer[3] - inner[3],
                        )
                    ]
                )
            if m.get("background") and m["kind"] in ("rectangle", "ellipse"):
                obj[NameObject("/IC")] = ArrayObject(
                    [FloatObject(v) for v in colour(m["background"])]
                )
            else:
                obj.pop("/IC", None)
        else:
            obj[NameObject("/QuadPoints")] = ArrayObject(
                [FloatObject(v) for q in m["quads"] for v in q]
            )
            obj[NameObject("/C")] = ArrayObject(
                [FloatObject(v) for v in colour(m["color"])]
            )
        appearance = PdfReader(io.BytesIO(base64.b64decode(m["appearance_pdf"])))
        ap_page = appearance.pages[0]
        stream = DecodedStreamObject()
        stream.set_data(ap_page.get_contents().get_data())
        box = bounds(m)
        w, h = box[2] - box[0], box[3] - box[1]
        stream.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): ArrayObject(
                    [FloatObject(v) for v in (0, 0, w, h)]
                ),
                NameObject("/Resources"): ap_page["/Resources"].clone(writer),
            }
        )
        if m["kind"] == "callout":
            obj[NameObject("/DR")] = stream["/Resources"]
            fonts = stream["/Resources"].get("/Font", {})
            if not fonts:
                raise ValueError("No usable font for annotation text")
            font_name = next(iter(fonts))
            obj[NameObject("/DA")] = TextStringObject(
                f"{font_name} {m['size']} Tf "
                + " ".join(map(str, colour(m["color"])))
                + " RG "
                + " ".join(map(str, colour(m["text_color"])))
                + " rg"
            )
            obj[NameObject("/Q")] = NumberObject(0)
        obj[NameObject("/AP")] = DictionaryObject(
            {NameObject("/N"): writer._add_object(stream)}
        )
        from datetime import datetime, timezone

        obj[NameObject("/M")] = TextStringObject(
            datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
        )
        clean["appearance_signature"] = signature(obj)
        obj[NameObject("/RepdfData")] = TextStringObject(
            json.dumps(clean, ensure_ascii=False)
        )
        if target is None:
            if "/Annots" not in page:
                page[NameObject("/Annots")] = annotations
            annotations.append(writer._add_object(obj))
    for page_index, page in enumerate(writer.pages):
        if "/Annots" in page:
            page[NameObject("/Annots")] = ArrayObject(
                [
                    ref
                    for index, ref in enumerate(page["/Annots"])
                    if (page_index, index) not in deleted_indices
                ]
            )
