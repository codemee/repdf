"""An isolated QApplication exercises macOS event delivery without Finder."""
import subprocess
import sys


def test_mac_file_event_startup_queue_and_export_queue(tmp_path):
    script = '''
import sys
from pathlib import Path
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QWidget
from repdf.desktop_open import DesktopApplication
app = DesktopApplication([])
class Window(QWidget):
    _export_running = False
    def __init__(self):
        super().__init__()
        self.requests = []
    def load_pdfs(self, paths):
        self.requests.append(paths)
path = sys.argv[1]
assert app.event(QFileOpenEvent(path))
assert app.pending_files == [path]
window = Window()
app.attach_window(window)
app.processEvents()
assert window.requests == [[Path(path)]]
window._export_running = True
app.open_files([path])
assert len(window.requests) == 1
window._export_running = False
app.deliver_pending()
assert window.requests == [[Path(path)], [Path(path)]]
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path / '中文.pdf')],
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
