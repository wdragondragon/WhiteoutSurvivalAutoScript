from PyQt5.QtWidgets import QWidget, QComboBox, QHBoxLayout
from PyQt5.QtCore import pyqtSignal


class EmulatorComboBoxWidget(QWidget):
    # 选中项变化信号，带上 emulator 名称和当前值
    currentTextChanged = pyqtSignal(str, str)

    def __init__(self, name: str, items: set[str], current: str = "", parent=None):
        super().__init__(parent)
        self.name = name

        self.combo = QComboBox()
        self.combo.addItems(items)
        if current:
            self.combo.setCurrentText(current)

        self.combo.currentTextChanged.connect(self._on_current_changed)

        layout = QHBoxLayout()
        layout.addWidget(self.combo)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def _on_current_changed(self, text):
        self.currentTextChanged.emit(self.name, text)

    def get_value(self) -> str:
        return self.combo.currentText()

    def set_value(self, value: str):
        self.combo.setCurrentText(value)

    def set_items(self, items: list[str]):
        current = self.combo.currentText()
        self.combo.clear()
        self.combo.addItems(items)
        if current in items:
            self.combo.setCurrentText(current)
