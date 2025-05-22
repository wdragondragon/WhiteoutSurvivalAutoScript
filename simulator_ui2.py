from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QCheckBox, QPushButton,
    QHBoxLayout, QVBoxLayout, QLabel, QComboBox, QHeaderView
)

import config_manager
from TaskConfigEditor import TaskConfigEditor
from config_manager import TaskConfigManager, ADB_PATH, LDCONSOLE_PATH
from emulator_executor import EmulatorExecutor
from simulator_manager import EmulatorManager
from task_executor import TaskExecutor


def create_status_icon(color, size):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(pixmap)


class EmulatorSelector(QWidget):
    def __init__(self, config_mgr):
        super().__init__()
        self.setWindowTitle("模拟器选择器")
        self.resize(900, 500)

        self.config_mgr = config_mgr
        self.task_config_manager: TaskConfigManager = TaskConfigManager()
        self.manager = EmulatorManager(config_mgr.get("adb_path", ADB_PATH),
                                       config_mgr.get("ldconsole_path", LDCONSOLE_PATH))

        self.status_icon_size = self.config_mgr.get("status_icon_size", 12)
        self.running_icon = create_status_icon("green", self.status_icon_size)
        self.stopped_icon = create_status_icon("gray", self.status_icon_size)

        self.selected_emulators = set(self.config_mgr.get_selected_emulators())

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["状态", "模拟器名称", "额外信息", "选择"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.task_config_editor = TaskConfigEditor()

        self.main_layout = QHBoxLayout()
        self.main_layout.addWidget(self.table)
        self.main_layout.addWidget(self.task_config_editor)

        self.select_all_button = QPushButton("全选")
        self.deselect_all_button = QPushButton("全不选")
        self.start_button = QPushButton("开始执行")
        self.status_label = QLabel("状态：空闲")

        self.config_name_combo = QComboBox()
        self.config_name_combo.setEditable(True)
        self.config_name_combo.setInsertPolicy(QComboBox.NoInsert)
        self.config_name_combo.activated[str].connect(self.load_config_from_file)

        self.save_button = QPushButton("保存配置")
        self.save_button.clicked.connect(self.save_config_to_file)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.select_all_button)
        btn_layout.addWidget(self.deselect_all_button)
        btn_layout.addStretch()
        btn_layout.addWidget(self.start_button)
        btn_layout.addWidget(self.save_button)

        main_layout = QVBoxLayout()
        main_layout.addLayout(self.main_layout)
        main_layout.addLayout(btn_layout)
        main_layout.addWidget(self.config_name_combo)
        main_layout.addWidget(self.status_label)
        self.setLayout(main_layout)

        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button.clicked.connect(self.deselect_all)
        self.start_button.clicked.connect(self.start_execution)

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_emulators)
        self.timer.start(5000)

        self.refresh_emulators()
        self.refresh_config_file_list()
        self.load_config_from_file(self.config_name_combo.currentText())

    def get_extra_info(self, emulator_name):
        # 你可以自定义这个方法来获取更多信息，比如从配置文件中读取
        return f"额外({emulator_name})"

    def refresh_config_file_list(self):
        self.config_name_combo.clear()
        config_name_list = self.task_config_manager.get_config_name_list()
        for config_name in config_name_list:
            self.config_name_combo.addItem(config_name)

    def load_config_from_file(self, config_name):
        print(f"加载配置{config_name}")
        task_config = self.task_config_manager.load_config_from_file(config_name)
        self.task_config_editor.load_config_editor(task_config)

    def save_config_to_file(self):
        task_config = self.task_config_editor.get_task_config()
        config_name = self.config_name_combo.currentText().strip()
        self.task_config_manager.save_config_to_file(config_name, task_config)

    def refresh_emulators(self):
        emulators = self.manager.get_all_emulators()
        old_selected = self.selected_emulators.copy()

        self.table.blockSignals(True)
        self.table.setRowCount(0)

        for row, emu in enumerate(emulators):
            self.table.insertRow(row)

            icon_item = QTableWidgetItem()
            icon_item.setIcon(self.running_icon if emu.is_running() else self.stopped_icon)
            self.table.setItem(row, 0, icon_item)

            name_item = QTableWidgetItem(emu.name)
            self.table.setItem(row, 1, name_item)

            extra_info = self.get_extra_info(emu.name)
            self.table.setItem(row, 2, QTableWidgetItem(extra_info))

            checkbox = QCheckBox()
            checkbox.setChecked(emu.name in old_selected)
            checkbox.stateChanged.connect(self.update_selected_emulators)
            self.table.setCellWidget(row, 3, checkbox)

        self.update_selected_emulators()
        self.table.blockSignals(False)

    def update_selected_emulators(self):
        self.selected_emulators.clear()
        for row in range(self.table.rowCount()):
            checkbox: QCheckBox = self.table.cellWidget(row, 3)
            if checkbox and checkbox.isChecked():
                name_item = self.table.item(row, 1)
                if name_item:
                    self.selected_emulators.add(name_item.text())

    def select_all(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            checkbox: QCheckBox = self.table.cellWidget(row, 3)
            if checkbox:
                checkbox.setChecked(True)
        self.update_selected_emulators()
        self.table.blockSignals(False)

    def deselect_all(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            checkbox: QCheckBox = self.table.cellWidget(row, 3)
            if checkbox:
                checkbox.setChecked(False)
        self.update_selected_emulators()
        self.table.blockSignals(False)

    def start_execution(self):
        if not self.selected_emulators:
            self.status_label.setText("⚠️ 请先选择要执行的模拟器")
            return

        self.status_label.setText("▶️ 任务进行中...")
        for name in self.selected_emulators:
            emulator = next((e for e in self.manager.get_all_emulators() if e.name == name), None)
            if not emulator:
                continue

            if not emulator.is_running():
                print(f"{emulator.name}未运行，跳过执行")
                continue

            emulator_executor = EmulatorExecutor(config_manager.ADB_PATH, emulator.name, emulator.device_name)
            task_executor = TaskExecutor(emulator_executor=emulator_executor)
            task_config_name = self.config_name_combo.currentText().strip()
            task_config = self.task_config_manager.load_config_from_file(task_config_name)
            task_executor.execute_task_config(task_config)

        self.status_label.setText("✔️ 任务完成")

    def get_selected_emulators(self):
        return list(self.selected_emulators)
