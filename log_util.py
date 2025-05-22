from PyQt5.QtCore import pyqtSignal


class Log:
    def __init__(self, log_pyqt_signal=None):
        self.log_pyqt_signal = log_pyqt_signal

    def print(self, msg: str):
        if self.log_pyqt_signal:
            self.log_pyqt_signal.emit(msg)
        print(msg)


log = Log()