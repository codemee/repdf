from __future__ import annotations

from repdf.strings import tr

import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject


class RepdfError(Exception):
    """Base error presented to the user."""


class UnsupportedEncryptedPdfError(RepdfError):
    """Base class retained for callers handling password-protected PDFs."""


class PasswordRequiredError(UnsupportedEncryptedPdfError):
    pass


class IncorrectPasswordError(UnsupportedEncryptedPdfError):
    pass


class InvalidPdfError(RepdfError):
    """Raised when a PDF cannot be parsed."""


class SelectionState(Enum):
    NONE = 0
    PARTIAL = 1
    ALL = 2


@dataclass(frozen=True)
class PdfInfo:
    path: Path
    page_count: int


@dataclass(frozen=True)
class DocumentSelection:
    source: Path
    pages: tuple[int, ...]
    password: str | None = field(default=None, repr=False, compare=False)
    annotation_changes: tuple = field(default=(), repr=False, compare=False)


def _unlock(reader: PdfReader, password: str | None) -> None:
    if not reader.is_encrypted:
        return
    try:
        if reader.decrypt("") or (password is not None and reader.decrypt(password)):
            return
    except Exception:
        raise UnsupportedEncryptedPdfError(tr('無法解密此 PDF，可能使用不支援的加密方式。')) from None
    if password is None:
        raise PasswordRequiredError(tr('此 PDF 需要輸入密碼。'))
    raise IncorrectPasswordError(tr('密碼不正確，請重新輸入。'))


def _prepare_documents(documents: Iterable[DocumentSelection]):
    prepared = []
    readers = {}
    for document in documents:
        if not document.pages:
            continue
        source = Path(document.source).resolve()
        if source not in readers:
            if not source.is_file():
                raise FileNotFoundError(tr('找不到來源 PDF 檔案：{p0}', p0=source))
            readers[source] = PdfReader(source)
            _unlock(readers[source], document.password)
            if document.annotation_changes:
                from repdf.annotation_data import apply_changes
                writer = PdfWriter(); writer.clone_document_from_reader(readers[source])
                apply_changes(writer, document.annotation_changes)
                import io
                buffer = io.BytesIO(); writer.write(buffer)
                readers[source] = PdfReader(io.BytesIO(buffer.getvalue()))
        reader = readers[source]
        if any(page < 0 or page >= len(reader.pages) for page in document.pages):
            raise IndexError(tr('選取的頁碼超出來源 PDF 範圍：{p0}', p0=source))
        prepared.append((source, reader, document.pages))
    if not prepared:
        raise ValueError(tr('請至少選取一頁。'))
    return prepared


def _copy_metadata(reader: PdfReader, writer: PdfWriter) -> None:
    if reader.metadata:
        writer.add_metadata({str(key): str(value) for key, value in reader.metadata.items()
                             if key and value is not None})


def indices_for_parity(page_count: int, odd: bool) -> set[int]:
    """Return zero-based indices for human-facing odd or even page numbers."""
    start = 0 if odd else 1
    return set(range(start, page_count, 2))


def parity_state(selected: set[int], page_count: int, odd: bool) -> SelectionState:
    group = indices_for_parity(page_count, odd)
    if not group or not (selected & group):
        return SelectionState.NONE
    if group <= selected:
        return SelectionState.ALL
    return SelectionState.PARTIAL


def set_parity(
    selected: set[int], page_count: int, odd: bool, enabled: bool
) -> set[int]:
    result = set(selected)
    group = indices_for_parity(page_count, odd)
    if enabled:
        result.update(group)
    else:
        result.difference_update(group)
    return result


def default_output_path(source: str | Path) -> Path:
    path = Path(source)
    return path.with_name(f"{path.stem}_selected.pdf")


def split_output_paths(destination: str | Path, count: int) -> list[Path]:
    path = Path(destination)
    digits = max(2, len(str(count)))
    return [path.with_name(f"{path.stem}_{number:0{digits}d}.pdf")
            for number in range(1, count + 1)]


def split_selected_pages(
    source: str | Path, destination: str | Path, selected: Iterable[int], *,
    overwrite: bool = False,
) -> list[Path]:
    ordered = sorted(selected) if isinstance(selected, (set, frozenset)) else list(dict.fromkeys(selected))
    return split_documents([DocumentSelection(Path(source), tuple(ordered))], destination,
                           overwrite=overwrite)


def split_documents(
    documents: Iterable[DocumentSelection], destination: str | Path, *,
    overwrite: bool = False, protected_sources: Iterable[Path] = (),
) -> list[Path]:
    prepared = _prepare_documents(documents)
    outputs = split_output_paths(Path(destination).resolve(), sum(len(pages) for _, _, pages in prepared))
    protected = {source for source, _, _ in prepared} | {Path(path).resolve() for path in protected_sources}
    if protected.intersection(outputs):
        raise ValueError(tr('輸出檔案不可覆蓋來源 PDF。'))
    if not overwrite and any(path.exists() for path in outputs):
        raise FileExistsError(tr('部分單頁檔案已存在，請確認覆蓋或更換檔名。'))
    outputs[0].parent.mkdir(parents=True, exist_ok=True)
    # Finish generating every page before publishing any output file.
    with tempfile.TemporaryDirectory(prefix=".repdf-split-", dir=outputs[0].parent) as staging:
        staged = []
        ordered = [(reader, page) for _, reader, pages in prepared for page in pages]
        for (reader, page), output in zip(ordered, outputs):
            writer = PdfWriter()
            writer.add_page(reader.pages[page])
            _copy_metadata(reader, writer)
            pending = Path(staging) / output.name
            with pending.open("wb") as stream:
                writer.write(stream)
                stream.flush()
                os.fsync(stream.fileno())
            staged.append(pending)
        published = 0
        try:
            for pending, output in zip(staged, outputs):
                if overwrite:
                    os.replace(pending, output)
                elif os.name == "nt":
                    # Windows rename is atomic and refuses an existing destination.
                    os.rename(pending, output)
                else:
                    # Exclusive publication also protects against files created during export.
                    os.link(pending, output)
                published += 1
        except OSError as exc:
            raise OSError(tr('拆分輸出失敗；已完成 {p0} / {p1} 個檔案。\n{p2}', p0=published, p1=len(outputs), p2=exc)) from exc
    return outputs


def inspect_pdf(source: str | Path, password: str | None = None, *, quick=False) -> PdfInfo:
    path = Path(source).resolve()
    if not path.is_file():
        raise InvalidPdfError(tr('找不到來源 PDF 檔案。'))
    try:
        reader = PdfReader(path)
        _unlock(reader, password)
        page_count = reader.trailer['/Root']['/Pages'].get('/Count') if quick else None
        if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count < 1:
            page_count = len(reader.pages)
    except UnsupportedEncryptedPdfError:
        raise
    except Exception as exc:
        raise InvalidPdfError(tr('無法讀取這個 PDF，檔案可能已損壞或格式不受支援。')) from exc
    if page_count == 0:
        raise InvalidPdfError(tr('這個 PDF 沒有可用的頁面。'))
    return PdfInfo(path=path, page_count=page_count)


def export_selected_pages(
    source: str | Path, destination: str | Path, selected: Iterable[int]
) -> int:
    ordered = (
        sorted(selected) if isinstance(selected, (set, frozenset))
        else list(dict.fromkeys(selected))
    )
    return export_documents([DocumentSelection(Path(source), tuple(ordered))], destination)


def export_documents(
    documents: Iterable[DocumentSelection], destination: str | Path, *,
    protected_sources: Iterable[Path] = (),
) -> int:
    prepared = _prepare_documents(documents)
    destination_path = Path(destination).resolve()
    protected = {source for source, _, _ in prepared} | {Path(path).resolve() for path in protected_sources}
    if destination_path in protected:
        raise ValueError(tr('輸出檔案不可覆蓋來源 PDF。'))

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        writer = PdfWriter()
        for _, reader, pages in prepared:
            for page_index in pages:
                writer.add_page(reader.pages[page_index])
        _copy_metadata(prepared[0][1], writer)

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".pdf", prefix=".repdf-", dir=destination_path.parent,
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            writer.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, destination_path)
        temp_path = None
        return sum(len(pages) for _, _, pages in prepared)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def save_document(source: Path, destination: Path, order: Iterable[int], *,
                  password: str | None = None, overwrite: bool = False, annotation_changes=()) -> int:
    """Save every page in order, preserving document objects and encryption."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    reader = PdfReader(source)
    _unlock(reader, password)
    order = list(order)
    if (any(type(index) is not int for index in order)
            or sorted(order) != list(range(len(reader.pages)))):
        raise ValueError(tr('存檔必須包含完整且不重複的頁面順序。'))
    if destination.exists() and destination != source and not overwrite:
        raise FileExistsError(tr('檔案已存在，請確認覆蓋或更換檔名。'))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    from repdf.annotation_data import apply_changes
    apply_changes(writer, annotation_changes)
    pages = list(writer.pages)
    # Some producers encode local destinations as page numbers rather than
    # page references. Convert these before changing the page tree.
    def reference_destination(container, key):
        destination = container.get(key)
        if (isinstance(destination, ArrayObject) and destination
                and isinstance(destination[0], int) and 0 <= destination[0] < len(pages)):
            destination[0] = pages[int(destination[0])].indirect_reference

    for obj in writer._objects:
        if isinstance(obj, DictionaryObject):
            reference_destination(obj, '/Dest')
            reference_destination(obj, '/OpenAction')
            if obj.get('/S') == '/GoTo':
                reference_destination(obj, '/D')
    root = writer._root_object['/Pages'].get_object()
    parent = writer._root_object.raw_get('/Pages')
    root[NameObject('/Kids')] = ArrayObject([pages[index].indirect_reference for index in order])
    root[NameObject('/Count')] = NumberObject(len(order))
    for page in pages:
        page[NameObject('/Parent')] = parent
    if '/PageLabels' in reader.trailer['/Root']:
        labels = reader.page_labels
        nums = ArrayObject()
        for position, index in enumerate(order):
            nums.extend([NumberObject(position), DictionaryObject({NameObject('/P'): TextStringObject(labels[index])})])
        writer._root_object[NameObject('/PageLabels')] = DictionaryObject({NameObject('/Nums'): nums})
    if reader.is_encrypted:
        from pypdf.constants import UserAccessPermissions
        permissions = UserAccessPermissions(reader.trailer['/Encrypt'].get('/P', 4294967292))
        writer.encrypt(password or '', owner_password=password or '',
                       permissions_flag=permissions, algorithm='AES-256')
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', prefix='.repdf-save-',
                                         dir=destination.parent, delete=False) as stream:
            pending = Path(stream.name)
            writer.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        if destination == source or overwrite:
            os.replace(pending, destination)
        elif os.name == 'nt':
            os.rename(pending, destination)
        else:
            os.link(pending, destination)
            pending.unlink()
        pending = None
        return len(order)
    finally:
        writer.close()
        if pending is not None:
            pending.unlink(missing_ok=True)
