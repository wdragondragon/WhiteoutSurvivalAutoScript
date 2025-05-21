from PyQt5.QtWidgets import (
    QWidget, QListWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QLabel, QSpinBox, QDoubleSpinBox, QMessageBox
)

from task_executor import TASK_REGISTRY


class TaskConfigEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.task_param_widgets = []
        self.task_config = []
        self.setWindowTitle("任务配置编辑器")
        self.init_ui()
        self.refresh_task_list_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()

        # 左侧：任务选择
        self.task_list = QListWidget()
        for name in TASK_REGISTRY:
            self.task_list.addItem(name)
        add_button = QPushButton("添加任务")
        add_button.clicked.connect(self.add_task_to_config)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("可选任务"))
        left_layout.addWidget(self.task_list)
        left_layout.addWidget(add_button)

        # 中间：当前任务配置
        self.config_list = QListWidget()
        self.config_list.currentRowChanged.connect(self.update_param_editor)

        btn_up = QPushButton("上移")
        btn_down = QPushButton("下移")
        btn_remove = QPushButton("移除")

        btn_up.clicked.connect(self.move_up)
        btn_down.clicked.connect(self.move_down)
        btn_remove.clicked.connect(self.remove_task)

        mid_layout = QVBoxLayout()
        mid_layout.addWidget(QLabel("当前配置"))
        mid_layout.addWidget(self.config_list)
        mid_layout.addWidget(btn_up)
        mid_layout.addWidget(btn_down)
        mid_layout.addWidget(btn_remove)

        # 右侧：参数表单
        self.param_layout = QFormLayout()
        self.param_container = QWidget()
        self.param_container.setLayout(self.param_layout)

        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("任务参数"))
        right_layout.addWidget(self.param_container)

        # 组合所有布局
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(mid_layout, 1)
        main_layout.addLayout(right_layout, 2)

        self.setLayout(main_layout)

    def add_task_to_config(self):
        selected = self.task_list.currentItem()
        if selected:
            name = selected.text()
            task_info = TASK_REGISTRY[name]
            # 默认参数填入
            params = {
                p["name"]: p.get("default", "")
                for p in task_info.get("param_defs", [])
            }
            self.task_config.append({"name": name, "params": params})
            self.refresh_task_list_ui()
            self.config_list.setCurrentRow(len(self.task_config) - 1)

    def refresh_task_list_ui(self):
        """刷新中间任务配置列表UI"""
        self.config_list.clear()
        for idx, task in enumerate(self.task_config):
            self.config_list.addItem(f"{idx + 1}. {task['name']}")

    def update_param_editor(self, index):
        for i in reversed(range(self.param_layout.count())):
            widget = self.param_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        if index < 0 or index >= len(self.task_config):
            return

        task = self.task_config[index]
        task_info = TASK_REGISTRY[task["name"]]
        self.task_param_widgets = []

        for param_def in task_info.get("param_defs", []):
            pname = param_def["name"]
            ptype = param_def["type"]
            default = task["params"].get(pname, param_def.get("default", ""))
            widget = None

            if ptype == "str":
                widget = QLineEdit()
                widget.setText(str(default))
            elif ptype == "int":
                widget = QSpinBox()
                widget.setRange(0, 9999)
                widget.setValue(int(default) if default != "" else 0)
            elif ptype == "float":
                widget = QDoubleSpinBox()
                widget.setRange(0.0, 1.0)
                widget.setSingleStep(0.01)
                widget.setValue(float(default) if default != "" else 0.0)
            else:
                widget = QLineEdit(str(default))

            self.param_layout.addRow(QLabel(param_def["desc"]), widget)
            self.task_param_widgets.append((pname, widget))

    def save_params(self):
        idx = self.config_list.currentRow()
        if idx < 0 or idx >= len(self.task_config):
            return
        for pname, widget in self.task_param_widgets:
            if isinstance(widget, QLineEdit):
                value = widget.text()
            elif isinstance(widget, QSpinBox) or isinstance(widget, QDoubleSpinBox):
                value = widget.value()
            else:
                value = widget.text()
            self.task_config[idx]["params"][pname] = value

    def move_up(self):
        row = self.config_list.currentRow()
        if row > 0:
            self.task_config[row], self.task_config[row - 1] = self.task_config[row - 1], self.task_config[row]
            self.refresh_task_list_ui()
            self.config_list.setCurrentRow(row - 1)

    def move_down(self):
        row = self.config_list.currentRow()
        if 0 <= row < len(self.task_config) - 1:
            self.task_config[row], self.task_config[row + 1] = self.task_config[row + 1], self.task_config[row]
            self.refresh_task_list_ui()
            self.config_list.setCurrentRow(row + 1)

    def remove_task(self):
        row = self.config_list.currentRow()
        if 0 <= row < len(self.task_config):
            self.task_config.pop(row)
            self.refresh_task_list_ui()

    def get_task_config(self):
        self.save_params()
        return self.task_config

    def load_config_editor(self, data):
        try:
            self.task_config = data.get("tasks", [])
            self.refresh_task_list_ui()
            self.config_list.setCurrentRow(0)
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"加载出错: {str(e)}")


# 示例用法（请放在主函数中运行）
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    from task_executor import TaskExecutor

    app = QApplication(sys.argv)
    executor = TaskExecutor("模拟器1")
    editor = TaskConfigEditor()
    editor.resize(900, 500)
    editor.show()
    sys.exit(app.exec_())
