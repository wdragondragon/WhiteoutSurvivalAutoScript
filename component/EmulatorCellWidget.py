from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QCheckBox, QLabel


class EmulatorCellWidget(QWidget):
    # 自定义信号：参数为名称(str) 和是否勾选(bool)
    checkedChanged = pyqtSignal(str, bool)

    def __init__(self, name, is_running, running_icon: QIcon, stopped_icon: QIcon, is_checked=False, parent=None):
        super().__init__(parent)

        self.running_icon = running_icon
        self.stopped_icon = stopped_icon

        # 状态（"running" or "stopped"）
        self.status = "running" if is_running else "stopped"
        self.name = name

        # 布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(5)

        # 复选框
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(is_checked)
        self.checkbox.stateChanged.connect(self._on_checkbox_changed)

        # 图标
        self.icon_label = QLabel()
        icon = self.running_icon if is_running else self.stopped_icon
        self.icon_label.setPixmap(icon.pixmap(16, 16))

        # 名称
        self.name_label = QLabel(name)

        layout.addWidget(self.checkbox)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.name_label)
        layout.addStretch()

    # 内部槽函数：当复选框变化时发出信号
    def _on_checkbox_changed(self, state):
        self.checkedChanged.emit(self.name, state == Qt.Checked)

    # === 公共方法 ===
    def is_checked(self):
        return self.checkbox.isChecked()

    def set_checked(self, value: bool):
        self.checkbox.setChecked(value)

    def get_status(self):
        return self.status

    def set_status(self, is_running: bool):
        self.status = "running" if is_running else "stopped"
        icon = self.running_icon if is_running else self.stopped_icon
        self.icon_label.setPixmap(icon.pixmap(16, 16))

    def get_name(self):
        return self.name

    def set_name(self, new_name: str):
        self.name = new_name
        self.name_label.setText(new_name)
