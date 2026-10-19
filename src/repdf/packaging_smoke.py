from __future__ import annotations

import json
import os
import tempfile
import traceback
from contextlib import ExitStack
from pathlib import Path


def _stop_backend(process):
    from repdf.renderer import RenderService
    RenderService(process).close(terminate_tree=True)


def main(report_path: str) -> int:
    report = Path(report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication
        from pypdf import PdfReader, PdfWriter
        from repdf import __version__
        from repdf.app import load_app_icon
        from repdf.core import DocumentSelection, export_selected_pages, export_documents, inspect_pdf, split_documents
        from repdf.renderer import start_render_backend
        from repdf.preferences import LanguageController
        from repdf.strings import tr
        from repdf.theme import ThemeController
        from repdf.ocr import _engine, recognize_region
        from repdf.search import compile_query
        import pypdfium2 as pdfium
        from PIL import Image, ImageDraw, ImageFont
        app = QApplication([])
        language = LanguageController("zh")
        if language.qt_translator.isEmpty():
            raise RuntimeError("Traditional Chinese dialog translations are missing")
        language.set_mode("en")
        if tr("第 {p0} 頁", p0=1) != "Page 1":
            raise RuntimeError("English translation failed")
        theme = ThemeController(app, "light")
        theme.set_mode("dark")
        language.close()
        if load_app_icon().isNull():
            raise RuntimeError("Application icon is missing")
        if not compile_query(r'sm.ke', regular_expression=True).search('SMOKE', timeout=1):
            raise RuntimeError('Search regular expression runtime failed')
        ocr_image = Image.new('RGB', (500, 100), 'white')
        ImageDraw.Draw(ocr_image).text((15, 15), 'Copy this text',
                                     font=ImageFont.load_default(size=48), fill='black')
        ocr_result = _engine()(ocr_image)
        if not ocr_result.txts or ocr_result.txts[0] != 'Copy this text':
            raise RuntimeError(f"Packaged OCR failed: {ocr_result.txts}")
        with tempfile.TemporaryDirectory(prefix="repdf-smoke-") as directory, ExitStack() as resources:
            root = Path(directory)
            ocr_source = root / 'ocr-image.pdf'
            ocr_image.save(ocr_source, 'PDF', resolution=72)
            ocr_document = pdfium.PdfDocument(ocr_source)
            try:
                ocr_page = ocr_document[0]
                try:
                    region_result = recognize_region(ocr_page, [0, 0], [1, 1])
                finally:
                    ocr_page.close()
            finally:
                ocr_document.close()
            if region_result['text'] != 'Copy this text':
                raise RuntimeError(f"Packaged region OCR failed: {region_result['text']}")
            source = root / "source.pdf"
            writer = PdfWriter()
            for width in (200, 300):
                writer.add_blank_page(width=width, height=400)
            with source.open("wb") as stream:
                writer.write(stream)
            process = start_render_backend()
            resources.callback(_stop_backend, process)
            process.stdin.write(json.dumps({
                "source": str(source), "output_dir": str(root),
                "scale": 0.5, "generation": 1,
            }) + "\n")
            process.stdin.flush()
            pages = []
            for line in process.stdout:
                message = json.loads(line)
                if message["type"] == "error":
                    raise RuntimeError(message["message"])
                if message["type"] == "page":
                    if QImage(message["path"]).isNull():
                        raise RuntimeError("Invalid rendered page")
                    pages.append(message["page"])
                if message["type"] == "done":
                    break
            if pages != [0, 1]:
                raise RuntimeError(f"Unexpected rendered pages: {pages}")
            from PySide6.QtCore import QEventLoop, QTimer
            from PySide6.QtPrintSupport import QPrinter
            from repdf.printing import PrintJob, PrintPage
            printed = root / 'printed.pdf'
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(str(printed))
            from repdf.print_preview import PrintPreviewDialog
            from PySide6.QtWidgets import QDialog
            preview = PrintPreviewDialog(printer, [PrintPage(source, 1), PrintPage(source, 0)])
            resources.callback(preview.cleanup)
            preview_poll = QTimer()
            def check_preview():
                if preview.print_button.isEnabled():
                    preview.accept()
                elif preview.status.text().startswith(tr('無法產生列印預覽：{p0}', p0='')):
                    preview.reject()
            preview_poll.timeout.connect(check_preview)
            preview_poll.start(20)
            preview_timeout = QTimer()
            preview_timeout.setSingleShot(True)
            preview_timeout.timeout.connect(preview.reject)
            preview_timeout.start(30000)
            preview_result = preview.exec()
            preview_poll.stop()
            preview_timeout.stop()
            if preview_result != QDialog.DialogCode.Accepted or printed.exists():
                raise RuntimeError(f'Packaged print preview failed: {preview.status.text()}')
            print_job = PrintJob(printer, [PrintPage(source, 1), PrintPage(source, 0)])
            resources.callback(print_job.cancel)
            loop = QEventLoop()
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(print_job.cancel)
            timer.start(30000)
            print_result = []
            print_job.finished.connect(lambda state, message: (print_result.append((state, message)), loop.quit()))
            QTimer.singleShot(0, print_job.start)
            loop.exec()
            timer.stop()
            if not print_result or print_result[0][0] != 'completed' or len(PdfReader(printed).pages) != 2:
                raise RuntimeError(f'Packaged printing failed: {print_result}')
            encrypted = root / 'encrypted.pdf'
            encrypted_writer = PdfWriter(clone_from=source)
            encrypted_writer.encrypt('smoke-password', algorithm='AES-256')
            encrypted_writer.write(encrypted)
            if inspect_pdf(encrypted, 'smoke-password').page_count != 2:
                raise RuntimeError('Encrypted PDF inspection failed')
            decrypted = root / 'decrypted.pdf'
            export_documents([DocumentSelection(encrypted, (0,), 'smoke-password')], decrypted)
            if PdfReader(decrypted).is_encrypted:
                raise RuntimeError('Unencrypted export from password-protected PDF failed')
            output = root / "reordered.pdf"
            export_selected_pages(source, output, [1, 0])
            if [int(page.mediabox.width) for page in PdfReader(output).pages] != [300, 200]:
                raise RuntimeError("Reordered export failed")
            second = root / "second.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=400, height=500)
            with second.open("wb") as stream:
                writer.write(stream)
            selections = [DocumentSelection(second, (0,)), DocumentSelection(source, (1, 0))]
            merged = root / "multi.pdf"
            export_documents(selections, merged)
            if [int(page.mediabox.width) for page in PdfReader(merged).pages] != [400, 300, 200]:
                raise RuntimeError("Multi-document export failed")
            single_pages = split_documents(selections, root / "single.pdf")
            if [int(PdfReader(path).pages[0].mediabox.width) for path in single_pages] != [400, 300, 200]:
                raise RuntimeError("Multi-document split failed")
        report.write_text(json.dumps({"ok": True, "version": __version__,
                                      "ocr_engine": "RapidOCR/ONNX Runtime",
                                      "ocr_text": ocr_result.txts[0]}), encoding="utf-8")
        return 0
    except Exception:
        report.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}), encoding="utf-8")
        return 1
