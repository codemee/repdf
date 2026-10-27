"""About dialog and offline license readers for source and installed builds."""
from importlib import metadata
from pathlib import Path
import re

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QPushButton, QSplitter, QTabWidget, QTextBrowser, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget)

from repdf import __version__
from repdf.strings import tr


def license_documents(package_dir=None, distribution=None):
    package = Path(package_dir) if package_dir else Path(__file__).resolve().parent
    documents = {}
    # Source checkout and frozen bundles have complete, offline notice trees.
    repository = package.parent.parent
    roots = [package / 'licenses', package / 'licenses/third-party']
    if (repository / 'pyproject.toml').is_file() and (repository / 'LICENSE').is_file():
        roots.append(repository)
    for root in roots:
        for name in ('LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md', 'PYTHON-LICENSE.txt', 'SOURCES.txt'):
            path = root / name
            if path.is_file():
                documents.setdefault(name, path)
    for root in (package / 'licenses/third-party', repository):
        notices = root / 'third_party/notices'
        if notices.is_dir():
            for path in sorted(notices.rglob('*')):
                if path.is_file():
                    documents.setdefault('third_party/' + path.relative_to(notices).as_posix(), path)
    environment = package / 'licenses/third-party/environment'
    if environment.is_dir():
        for path in sorted(environment.rglob('*')):
            if path.is_file():
                documents['environment/' + path.relative_to(environment).as_posix()] = path
    # A Python wheel carries project terms in dist-info/licenses. Dependencies
    # are separate distributions: expose their installed notices as well.
    try:
        dist = distribution if distribution is not None else metadata.distribution('repdf')
        for file in dist.files or ():
            if file.name in ('LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md') and '.dist-info' in str(file):
                path = Path(dist.locate_file(file))
                if path.is_file():
                    documents.setdefault(file.name, path)
    except metadata.PackageNotFoundError:
        pass
    if not any(name.startswith(('third_party/', 'environment/')) for name in documents):
        for dist in metadata.distributions():
            name = dist.metadata['Name']
            if name.lower() == 'repdf':
                continue
            for file in dist.files or ():
                if '..' in file.parts or not any(re.search(r'license|licence|notice|copying', part, re.I) for part in file.parts):
                    continue
                path = Path(dist.locate_file(file))
                if path.is_file():
                    documents[f'environment/{name}/{file}'] = path
    return documents


class AboutDialog(QDialog):
    def __init__(self, parent=None, *, documents=None):
        super().__init__(parent)
        self.documents = license_documents() if documents is None else documents
        self.resize(680, 520)
        self.setMinimumSize(420, 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(16)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QApplication.windowIcon().pixmap(QSize(56, 56)))
        header.addWidget(icon)
        title = QLabel(f'RePDF {__version__}\nRead the PDF')
        font = title.font()
        font.setPointSizeF(font.pointSizeF() + 3)
        title.setFont(font)
        header.addWidget(title, 1)
        layout.addLayout(header)
        self.tabs = QTabWidget()
        self.overview = QWidget()
        overview = QVBoxLayout(self.overview)
        overview.setContentsMargins(16, 18, 16, 18)
        overview.addWidget(QLabel('Copyright © 2026 Shin-Wei Hwang'))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        overview.addWidget(self.summary)
        overview.addStretch()
        self.source_button = QPushButton()
        self.source_button.setMinimumHeight(34)
        self.source_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://github.com/codemee/repdf')))
        overview.addWidget(self.source_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.tabs.addTab(self.overview, '')
        self.license_text = QTextBrowser()
        self.license_text.setOpenLinks(False)
        self.license_text.setPlainText(self.read_document('LICENSE'))
        self.tabs.addTab(self.license_text, '')
        third_party = QSplitter(Qt.Orientation.Horizontal)
        self.notice_tree = QTreeWidget()
        self.notice_tree.setHeaderHidden(True)
        self.notice_tree.setMinimumWidth(140)
        self.notice_text = QTextBrowser()
        self.notice_text.setOpenLinks(False)
        third_party.addWidget(self.notice_tree)
        third_party.addWidget(self.notice_text)
        third_party.setSizes([220, 410])
        self.tabs.addTab(third_party, '')
        branches = {}
        for name in sorted(self.documents):
            if name == 'LICENSE':
                continue
            parts = name.split('/')
            for index in range(1, len(parts) + 1):
                key = '/'.join(parts[:index])
                if key not in branches:
                    parent_item = branches.get('/'.join(parts[:index - 1]), self.notice_tree)
                    item = QTreeWidgetItem(parent_item, [parts[index - 1]])
                    branches[key] = item
            item = branches[name]
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            item.setToolTip(0, name)
        self.notice_tree.currentItemChanged.connect(self.select_notice)
        default = branches.get('THIRD_PARTY_NOTICES.md') or branches.get('NOTICE')
        if default is not None:
            self.notice_tree.setCurrentItem(default)
        layout.addWidget(self.tabs, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setMinimumSize(88, 34)
        layout.addWidget(self.buttons)
        self.retranslate()

    def read_document(self, name):
        try:
            return self.documents[name].read_text(encoding='utf-8', errors='replace')
        except (KeyError, OSError):
            return tr('找不到授權文件；請查看原始碼儲存庫隨附的 LICENSE 與第三方授權聲明。')

    def select_notice(self, item, _previous=None):
        name = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self.notice_text.setPlainText(self.read_document(name) if name else '')

    def retranslate(self):
        self.setWindowTitle(tr('關於 RePDF'))
        self.tabs.setTabText(0, tr('關於'))
        self.tabs.setTabText(1, tr('完整授權'))
        self.tabs.setTabText(2, tr('第三方授權'))
        self.summary.setText(tr('本程式採用 GNU GPL 第 3 版（GPL-3.0-only），允許使用、修改與商用；散布時須遵守授權條款並提供對應原始碼。\n\n本程式不提供任何擔保。第三方程式庫與 OCR 模型維持各自的授權。'))
        self.source_button.setText(tr('查看原始碼'))
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr('關閉'))
