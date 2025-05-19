from PyQt5.QtWidgets import (
    QWidget, QListWidget, QFormLayout, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout, QSpinBox, QDoubleSpinBox,
    QPushButton, QComboBox, QMessageBox, QScrollArea
)

from task_executor import TASK_REGISTRY


class TaskSelectorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.task_list = QListWidget()
        self.form_layout = QFormLayout()
        self.form_container = QWidget()
        self.form_container.setLayout(self.form_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.form_container)

        self.execute_button = QPushButton("执行任务")
        self.execute_button.clicked.connect(self.on_execute)

        self.params_widgets = {}
        self.current_task = None

        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("任务列表"))
        left_panel.addWidget(self.task_list)

        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("任务参数"))
        right_panel.addWidget(self.scroll_area)
        right_panel.addWidget(self.execute_button)

        layout = QHBoxLayout()
        layout.addLayout(left_panel, 1)
        layout.addLayout(right_panel, 2)
        self.setLayout(layout)

        self.task_list.addItems(list(TASK_REGISTRY.keys()))
        self.task_list.currentTextChanged.connect(self.load_task_form)

    def load_task_form(self, task_name):
        # 清空旧表单
        for i in reversed(range(self.form_layout.count())):
            self.form_layout.itemAt(i).widget().deleteLater()
        self.params_widgets.clear()
        self.current_task = task_name

        task_info = TASK_REGISTRY.get(task_name)
        if not task_info:
            return

        for param in task_info.get("param_defs", []):
            name = param["name"]
            ptype = param["type"]
            default = param.get("default")
            desc = param.get("desc", name)

            widget = None
            if ptype == "int":
                widget = QSpinBox()
                widget.setMaximum(999999)
                if default is not None:
                    widget.setValue(int(default))
            elif ptype == "float":
                widget = QDoubleSpinBox()
                widget.setDecimals(3)
                widget.setSingleStep(0.01)
                widget.setMaximum(1.0)
                if default is not None:
                    widget.setValue(float(default))
            elif ptype == "str":
                widget = QLineEdit()
                if default is not None:
                    widget.setText(str(default))
            elif ptype == "choice":
                widget = QComboBox()
                for option in param.get("options", []):
                    widget.addItem(option)
                if default in param.get("options", []):
                    widget.setCurrentText(default)
            else:
                widget = QLabel(f"不支持的参数类型: {ptype}")

            self.form_layout.addRow(f"{desc}:", widget)
            self.params_widgets[name] = (widget, ptype)

    def get_current_params(self):
        """返回当前表单中的参数字典"""
        result = {}
        for name, (widget, ptype) in self.params_widgets.items():
            if isinstance(widget, QLineEdit):
                result[name] = widget.text()
            elif isinstance(widget, QSpinBox) or isinstance(widget, QDoubleSpinBox):
                result[name] = widget.value()
            elif isinstance(widget, QComboBox):
                result[name] = widget.currentText()
        return result

    def validate_params(self):
        """简单参数校验，如果有错误返回 False"""
        valid = True
        for name, (widget, ptype) in self.params_widgets.items():
            if ptype == "str" and isinstance(widget, QLineEdit):
                if not widget.text().strip():
                    widget.setStyleSheet("border: 1px solid red;")
                    valid = False
                else:
                    widget.setStyleSheet("")
            else:
                widget.setStyleSheet("")
        return valid

    def on_execute(self):
        if not self.current_task:
            QMessageBox.warning(self, "提示", "请选择一个任务")
            return
        if not self.validate_params():
            QMessageBox.warning(self, "提示", "请填写完整参数")
            return

        params = self.get_current_params()
        QMessageBox.information(self, "任务参数", f"任务: {self.current_task}\n参数: {params}")
        # 你可以在这里调用实际任务执行函数，例如：
        # self.executor.execute_task(self.current_task, params)


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    win = TaskSelectorWidget()
    win.setWindowTitle("任务选择器")
    win.resize(600, 400)
    win.show()
    sys.exit(app.exec_())
