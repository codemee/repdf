"""Ten successful PDF opens, shared by toolbar history and Windows Shell."""
from pathlib import Path
import os

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMenu, QMessageBox

from repdf.strings import tr
from repdf.windows_recent import publish_recent_document


class RecentFiles(QObject):
    LIMIT = 10
    KEY = 'files/recent'

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.menu = QMenu(tr('最近開啟的檔案'), owner)
        self.menu.setToolTipsVisible(True)
        self.menu.aboutToShow.connect(self.populate)
        self.populate()

    def paths(self):
        values = self.owner.settings.value(self.KEY, [])
        if isinstance(values, str):
            values = [values]
        result, seen = [], set()
        for value in values or []:
            path = Path(value)
            key = os.path.normcase(str(path))
            if key not in seen:
                result.append(path)
                seen.add(key)
        return result[:self.LIMIT]

    def record(self, path):
        path = Path(path).resolve()
        if not path.is_file():
            return
        key = os.path.normcase(str(path))
        paths = [path] + [p for p in self.paths() if os.path.normcase(str(p)) != key]
        self.owner.settings.setValue(self.KEY, [str(p) for p in paths[:self.LIMIT]])
        publish_recent_document(path)

    def populate(self):
        self.menu.clear()
        self.menu.setTitle(tr('最近開啟的檔案'))
        paths = self.paths()
        if not paths:
            self.menu.addAction(tr('尚無最近開啟的檔案')).setEnabled(False)
        for index, path in enumerate(paths, 1):
            action = self.menu.addAction(f'&{index}  ' + path.name.replace('&', '&&'))
            action.setToolTip(str(path))
            action.setData(str(path))
            action.triggered.connect(lambda _checked=False, path=path: self.open(path))

    def open(self, path):
        if not path.is_file():
            QMessageBox.warning(self.owner, tr('無法開啟檔案'), tr('檔案不存在或無法存取：{path}', path=path))
            return
        self.owner.load_pdf(path)
