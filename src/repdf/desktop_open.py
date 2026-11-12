"""Desktop file opening and per-user single-instance delivery."""
import json
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QEvent, QLockFile, QObject, QStandardPaths, QThread, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication
from repdf.early_open import file_arguments, instance_name


def send_paths(socket, paths, timeout=5000):
    """Drain the full request, including completions racing Qt's wait call."""
    payload = json.dumps(paths, ensure_ascii=False).encode('utf-8') + b'\n'
    error = 'Could not deliver files to RePDF. Please retry.'
    if socket.write(payload) != len(payload):
        raise RuntimeError(error)
    timer = QElapsedTimer()
    timer.start()
    while socket.bytesToWrite():
        remaining = timeout - timer.elapsed()
        if remaining <= 0 or not socket.waitForBytesWritten(remaining):
            # On Windows an asynchronous completion can drain the queue before
            # waitForBytesWritten starts waiting; Qt then returns false because
            # there is no pending write. That is not a delivery failure.
            if socket.bytesToWrite():
                raise RuntimeError(error)
    socket.disconnectFromServer()


class DesktopApplication(QApplication):
    def __init__(self, arguments):
        super().__init__(arguments)
        self.window = None
        self.pending_files = []
        self.delivery_timer = QTimer(self)
        self.delivery_timer.setSingleShot(True)
        self.delivery_timer.timeout.connect(self.deliver_pending)

    def event(self, event):
        if event.type() == QEvent.Type.FileOpen:
            path = event.file() or event.url().toLocalFile()
            if path:
                self.open_files([path])
                return True
        return super().event(event)

    def open_files(self, paths):
        if getattr(self, 'window', None) is None or getattr(self.window, '_export_running', False):
            self.pending_files.extend(paths)
            if self.window is not None:
                self.delivery_timer.start(150)
            return
        if paths:
            self.window.load_pdfs([Path(path) for path in paths])
        if self.window.isMinimized():
            self.window.showNormal()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def deliver_pending(self):
        paths, self.pending_files = self.pending_files, []
        self.open_files(paths)

    def attach_window(self, window):
        self.window = window
        paths, self.pending_files = self.pending_files, []
        QTimer.singleShot(0, lambda: self.open_files(paths))


class DesktopInstance(QObject):
    """A lock guards stale socket removal; only the lock owner may listen."""
    def __init__(self, app, name=None):
        super().__init__(app)
        self.name = name or instance_name()
        directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation))
        self.lock = QLockFile(str(directory / (self.name + '.lock')))
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.accept_connections)
        self.app = app
        self.buffers = {}

    def start(self, paths):
        if not self.lock.tryLock(0):
            socket = QLocalSocket()
            timer = QElapsedTimer()
            timer.start()
            while timer.elapsed() < 5000:
                socket.connectToServer(self.name)
                if socket.waitForConnected(250):
                    break
                socket.abort()
                QThread.msleep(50)
            if socket.state() != QLocalSocket.LocalSocketState.ConnectedState:
                raise RuntimeError('Cannot contact the running RePDF window. Please retry.')
            send_paths(socket, paths)
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise RuntimeError(self.server.errorString())
        self.app.open_files(paths)
        return True

    def accept_connections(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.buffers[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self.read_request(s))
            socket.disconnected.connect(lambda s=socket: self.drop_connection(s))
            self.read_request(socket)

    def read_request(self, socket):
        buffer = self.buffers.get(socket)
        if buffer is None:
            return
        buffer.extend(bytes(socket.readAll()))
        if len(buffer) > 1024 * 1024:
            socket.abort()
            return
        if b'\n' not in buffer:
            return
        try:
            paths = json.loads(bytes(buffer).split(b'\n', 1)[0])
            if isinstance(paths, list) and all(isinstance(p, str) and Path(p).is_absolute() for p in paths):
                self.app.open_files(paths)
        except (ValueError, OSError):
            pass
        self.buffers.pop(socket, None)
        # The sender closes after its write completes. Closing the Windows pipe
        # here can race the sender's completion notification.

    def drop_connection(self, socket):
        self.read_request(socket)
        self.buffers.pop(socket, None)
        socket.deleteLater()

    def close(self):
        self.server.close()
        self.lock.unlock()
