from PyQt5.QtWidgets import (
    QWidget, QListWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QLabel, QSpinBox, QDoubleSpinBox, QMessageBox, QComboBox
)

from task_executor import TASK_REGISTRY
import json
import os


class TaskConfigEditor(QWidget):
    def __init__(self, executor=None):
        super().__init__()
        self.executor = executor
        self.task_param_widgets = []
        self.task_config = []
        self.setWindowTitle("任务配置编辑器")
        self.init_ui()
        self.refresh_task_list_ui()
        self.refresh_config_file_list()

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

        self.save_button = QPushButton("保存配置")
        self.save_button.clicked.connect(self.save_config_to_file)

        # 底部：配置命名与执行
        self.config_name_combo = QComboBox()
        self.config_name_combo.setEditable(True)
        self.config_name_combo.setInsertPolicy(QComboBox.NoInsert)
        self.config_name_combo.activated[str].connect(self.load_config_from_file)
        self.execute_button = QPushButton("执行任务配置")
        self.execute_button.clicked.connect(self.execute_config)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(QLabel("配置名:"))
        bottom_layout.addWidget(self.config_name_combo)
        bottom_layout.addWidget(self.save_button)
        bottom_layout.addWidget(self.execute_button)

        # 组合所有布局
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(mid_layout, 1)
        main_layout.addLayout(right_layout, 2)

        root_layout = QVBoxLayout()
        root_layout.addLayout(main_layout)
        root_layout.addLayout(bottom_layout)

        self.setLayout(root_layout)

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

    def refresh_config_file_list(self):
        """刷新配置文件名下拉框"""
        self.config_name_combo.clear()
        if not os.path.exists("configs"):
            return
        for fname in os.listdir("configs"):
            if fname.endswith(".json"):
                self.config_name_combo.addItem(fname[:-5])

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

    def execute_config(self):
        self.save_params()
        if not self.executor:
            QMessageBox.warning(self, "执行失败", "未绑定 EmulatorExecutor")
            return
        name = self.config_name_combo.currentText().strip() or "未命名配置"
        print(f"开始执行任务配置: {name}")
        self.executor.execute_task_config({"tasks": self.task_config})

    def save_config_to_file(self):
        self.save_params()
        config_name = self.config_name_combo.currentText().strip()
        if not config_name:
            QMessageBox.warning(self, "保存失败", "请填写配置名")
            return

        data = {
            "name": config_name,
            "tasks": self.task_config
        }

        os.makedirs("configs", exist_ok=True)
        path = os.path.join("configs", f"{config_name}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "保存成功", f"配置已保存至 {path}")
            # 保存成功后刷新下拉框，确保新配置显示
            self.refresh_config_file_list()
            self.config_name_combo.setCurrentText(config_name)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存出错: {str(e)}")

    def load_config_from_file(self, config_name):
        path = os.path.join("configs", f"{config_name}.json")
        if not os.path.exists(path):
            QMessageBox.warning(self, "配置不存在", f"{path} 不存在")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.task_config = data.get("tasks", [])
            self.config_name_combo.setCurrentText(data.get("name", config_name))
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
    editor = TaskConfigEditor(executor)
    editor.resize(900, 500)
    editor.show()
    sys.exit(app.exec_())
