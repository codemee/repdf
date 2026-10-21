"""Language selection and cancellable downloads for source and frozen applications."""
from __future__ import annotations

import hashlib

from PySide6.QtCore import QObject, QIODevice, QSaveFile, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QMenu,
                              QProgressBar, QVBoxLayout)

from repdf.ocr_models import PROFILES, installed_profiles, model_available, model_path
from repdf.strings import tr


class OcrModelDialog(QDialog):
    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.reply = None
        self.file = None
        self.network = QNetworkAccessManager(self)
        self.setWindowTitle(tr('下載 OCR 語言模型'))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(460, 250)
        layout = QVBoxLayout(self)
        self.message = QLabel(tr('「{language}」需要額外下載模型。確認後將從 RapidOCR 官方模型來源下載至使用者資料目錄；完成後可離線使用，不會上傳 PDF。',
                                 language=tr(PROFILES[profile]['label'])))
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        source = QLabel('https://www.modelscope.cn/models/RapidAI/RapidOCR')
        source.setWordWrap(True)
        source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(source)
        self.status = QLabel(tr('下載完成後才會切換辨識語言；取消則保留原設定。'))
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.download_button = buttons.addButton(tr('下載並使用'), QDialogButtonBox.ButtonRole.ActionRole)
        self.download_button.clicked.connect(self.start)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180_000)
        self.timer.timeout.connect(lambda: self._fail(tr('下載逾時，請稍後重試。')))

    def start(self):
        if self.reply is not None:
            return
        try:
            destination = model_path(self.profile)
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.file = QSaveFile(str(destination))
            if not self.file.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(self.file.errorString())
        except OSError as exc:
            self._fail(str(exc))
            return
        self.digest = hashlib.sha256()
        self.received = 0
        self.download_button.setEnabled(False)
        self.status.setText(tr('正在下載模型…'))
        self.progress.setRange(0, 0)
        request = QNetworkRequest(QUrl(PROFILES[self.profile]['url']))
        request.setTransferTimeout(30_000)
        self.reply = self.network.get(request)
        self.reply.readyRead.connect(self._read)
        self.reply.downloadProgress.connect(self._progress)
        self.reply.finished.connect(self._finished)
        self.timer.start()

    def _progress(self, received, total):
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(received * 100 / total))

    def _read(self):
        if self.reply is None:
            return
        data = bytes(self.reply.readAll())
        self.received += len(data)
        if self.received > 100_000_000:
            self._fail(tr('下載檔案大小異常。'))
        elif self.file.write(data) != len(data):
            self._fail(self.file.errorString())
        else:
            self.digest.update(data)

    def _finished(self):
        if self.reply is None:
            return
        self._read()
        if self.reply is None:
            return
        if self.reply.error() != QNetworkReply.NetworkError.NoError:
            self._fail(self.reply.errorString())
            return
        if self.digest.hexdigest() != PROFILES[self.profile]['sha256']:
            self._fail(tr('模型校驗失敗，請重新下載。'))
            return
        if not self.file.commit():
            self._fail(self.file.errorString())
            return
        self.file = None
        self._cleanup()
        self.accept()

    def _cleanup(self):
        self.timer.stop()
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()
            reply.deleteLater()
        if self.file is not None:
            self.file.cancelWriting()
            self.file = None

    def _fail(self, reason):
        self._cleanup()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(tr('下載未完成：{reason}', reason=reason))
        self.download_button.setEnabled(True)

    def reject(self):
        self._cleanup()
        super().reject()


class OcrLanguageController(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        saved = owner.settings.value('ocr/language', 'builtin')
        self.profile = saved if saved in PROFILES else 'builtin'
        self.dialog = None
        self.callbacks = []
        self.menu = QMenu(owner)
        self.group = QActionGroup(self)
        self.actions = {}
        self._menu_signature = None
        for profile, info in PROFILES.items():
            action = QAction(tr(info['label']), self)
            action.setCheckable(True)
            self.group.addAction(action)
            action.triggered.connect(lambda _checked=False, profile=profile: self.choose(profile))
            self.actions[profile] = action
        self.menu.aboutToShow.connect(self.refresh)
        self.refresh()

    def refresh(self):
        installed = installed_profiles()
        signature = installed
        if signature != self._menu_signature:
            self.menu.clear()
            self.menu.addAction(self.actions['builtin'])
            self.menu.addAction(self.actions['auto'])
            self.menu.addSeparator()
            for profile in installed:
                self.menu.addAction(self.actions[profile])
            self.menu.addSeparator()
            for profile, info in PROFILES.items():
                if 'url' in info and profile not in installed:
                    self.menu.addAction(self.actions[profile])
            self._menu_signature = signature
        for profile, action in self.actions.items():
            label = tr(PROFILES[profile]['label'])
            action.setText(tr('{language}（已下載）', language=label) if profile in installed else label)
            action.setChecked(profile == self.profile)
        self.menu.setTitle(tr('OCR 辨識語言'))
        self.owner.region_ocr_action.setToolTip(tr('區域 OCR：框選頁面或圖片中的文字。辨識語言：{language}；按旁邊箭頭切換。',
                                                    language=tr(PROFILES[self.profile]['label'])))

    def choose(self, profile):
        def apply():
            self.profile = profile
            self.owner.settings.setValue('ocr/language', profile)
            # Results from an older language must not overwrite a newer selection.
            self.owner._text_requests.clear()
            self.owner._ocr_generations.clear()
            self.refresh()
        self.ensure(profile, apply)
        self.refresh()

    def ensure(self, profile, callback):
        if self.owner._closing:
            return
        if model_available(profile):
            callback()
            return
        if self.dialog is not None:
            if self.dialog.profile == profile:
                self.callbacks.append(callback)
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        self.callbacks = [callback]
        self.dialog = OcrModelDialog(profile, self.owner._fullscreen_preview or self.owner)
        self.dialog.finished.connect(self._finished)
        self.dialog.open()

    def _finished(self, result):
        dialog, self.dialog = self.dialog, None
        callbacks, self.callbacks = self.callbacks, []
        dialog.deleteLater()
        if result == QDialog.DialogCode.Accepted and not self.owner._closing:
            for callback in callbacks:
                callback()
        self.refresh()

    def close(self):
        self.callbacks.clear()
        if self.dialog is not None:
            self.dialog.reject()
