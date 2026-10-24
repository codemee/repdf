"""Keep button hints synchronized with their actual QAction shortcuts."""

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QKeySequence

from repdf.strings import localize_text, tr


def native_shortcuts(sequences):
    labels = []
    for sequence in sequences:
        portable = sequence.toString(QKeySequence.SequenceFormat.PortableText)
        if not portable or portable == 'Close':
            continue
        label = QKeySequence(portable.replace('Backtab', 'Tab')).toString(
            QKeySequence.SequenceFormat.NativeText
        )
        if label not in labels:
            labels.append(label)
    return ' / '.join(labels)


def shortcut_tooltip(text, sequences):
    keys = native_shortcuts(sequences)
    return text + '\n' + tr('快捷鍵：{keys}', keys=keys) if keys else text


class ShortcutHints(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.updating = False
        self.actions = [action for action in owner.findChildren(QAction) if action.shortcuts()]
        for action in self.actions:
            action.changed.connect(lambda action=action: self.update_action(action))
        self.refresh()

    def update_action(self, action):
        if self.updating:
            return
        self.updating = True
        try:
            text = action.toolTip()
            for marker in ('\n快捷鍵：', '\nShortcuts: '):
                text = text.split(marker, 1)[0]
            if action is self.owner.zoom_reset_action:
                text = tr('縮放：25%–200%；點擊比例回到 100%。\n放大：{up}\n縮小：{down}\n100% 以 96 DPI 顯示 PDF 頁面。',
                          up=native_shortcuts(self.owner.zoom_in_action.shortcuts()),
                          down=native_shortcuts(self.owner.zoom_out_action.shortcuts()))
            action.setToolTip(shortcut_tooltip(localize_text(text), action.shortcuts()))
        finally:
            self.updating = False

    def refresh(self):
        for action in self.actions:
            self.update_action(action)
        for action in (self.owner.single_action, self.owner.spread_action, self.owner.cover_action):
            text = action.toolTip()
            for marker in ('\nF11：', '\nF11: '):
                text = text.split(marker, 1)[0]
            action.setToolTip(localize_text(text) + '\n' + tr('F11：使用上次選擇的全螢幕模式'))
