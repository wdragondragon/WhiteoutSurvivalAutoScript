# simulator_ui.py
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtWidgets import (
    QWidget, QListWidget, QPushButton, QHBoxLayout, QVBoxLayout,
    QListWidgetItem, QLabel, QComboBox, QTabWidget, QTextEdit
)

import config_manager
import log_util
from TaskConfigEditor import TaskConfigEditor
from config_manager import TaskConfigManager, ADB_PATH, LDCONSOLE_PATH
from emulator_executor import EmulatorExecutor
from log_util import Log, log
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


class TaskThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)

    def __init__(self, emulator, task_config, adb_path):
        super().__init__()
        self.emulator = emulator
        self.task_config = task_config
        self.adb_path = adb_path
        self._is_running = True

    def run(self):
        if not self.emulator.is_running():
            self.log_signal.emit(f"⚠️ 模拟器 {self.emulator.name} 未运行，跳过")
            self.finished_signal.emit(self.emulator.name)
            return

        executor = EmulatorExecutor(config_manager.ADB_PATH, self.emulator.name, self.emulator.device_name)
        task_executor = TaskExecutor(emulator_executor=executor)

        while self._is_running:
            task_executor.execute_task_config(self.task_config)
            self.log_signal.emit(f"✅ {self.emulator.name} 执行完毕，3秒后再次执行")
            self.sleep(3)

        self.finished_signal.emit(self.emulator.name)

    def stop(self):
        self._is_running = False


class EmulatorSelector(QWidget):
    log_pyqt_signal = pyqtSignal(str)

    def __init__(self, config_mgr):
        super().__init__()
        self.setWindowTitle("模拟器选择器")
        self.resize(1200, 400)
        log_util.log = Log(self.log_pyqt_signal)
        self.threads = {}
        self.is_running = False
        self.config_mgr = config_mgr
        self.task_config_manager: TaskConfigManager = TaskConfigManager()

        self.manager = EmulatorManager(config_mgr.get("adb_path", ADB_PATH),
                                       config_mgr.get("ldconsole_path", LDCONSOLE_PATH))
        self.status_icon_size = self.config_mgr.get("status_icon_size", 12)
        self.running_icon = create_status_icon("green", self.status_icon_size)
        self.stopped_icon = create_status_icon("gray", self.status_icon_size)

        self.selected_emulators = set(self.config_mgr.get_selected_emulators())

        # UI 部件
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)

        self.task_config_editor = TaskConfigEditor()

        self.main_layout = QHBoxLayout()
        self.main_layout.addWidget(self.list_widget)
        self.main_layout.addWidget(self.task_config_editor)

        self.select_all_button = QPushButton("全选")
        self.deselect_all_button = QPushButton("全不选")
        self.start_button = QPushButton("开始执行")
        self.status_label = QLabel("状态：空闲")

        # 底部：配置命名与执行
        self.config_name_combo = QComboBox()
        self.config_name_combo.setEditable(True)
        self.config_name_combo.setInsertPolicy(QComboBox.NoInsert)
        self.config_name_combo.activated[str].connect(self.load_config_from_file)

        self.save_button = QPushButton("保存配置")
        self.save_button.clicked.connect(self.save_config_to_file)
        # 布局
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
        self.main_tab = QWidget()
        self.main_tab.setLayout(main_layout)

        self.log_text = QTextEdit()
        self.log_text.document().setMaximumBlockCount(1000)
        self.log_text.setReadOnly(True)
        self.log_pyqt_signal.connect(self.log_text.append)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.main_tab, "配置")
        self.tab_widget.addTab(self.log_text, "日志")

        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

        # 连接信号槽
        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button.clicked.connect(self.deselect_all)
        self.start_button.clicked.connect(self.toggle_execution)
        self.list_widget.itemChanged.connect(self.handle_item_changed)

        # 定时刷新模拟器状态
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_emulators)
        self.timer.start(5000)  # 5秒刷新一次

        self.refresh_emulators()
        self.refresh_config_file_list()
        self.load_config_from_file(self.config_name_combo.currentText())

    def load_config_from_file(self, config_name):
        log_util.log.print(f"加载配置{config_name}")
        task_config = self.task_config_manager.load_config_from_file(config_name)
        self.task_config_editor.load_config_editor(task_config)

    def refresh_config_file_list(self):
        self.config_name_combo.clear()
        config_name_list = self.task_config_manager.get_config_name_list()
        for config_name in config_name_list:
            self.config_name_combo.addItem(config_name)

    def save_config_to_file(self):
        task_config = self.task_config_editor.get_task_config()
        config_name = self.config_name_combo.currentText().strip()
        self.task_config_manager.save_config_to_file(config_name, task_config)

    def refresh_emulators(self):
        emulators = self.manager.get_all_emulators()

        # 保留旧选中状态
        old_selected = self.selected_emulators.copy()

        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        for emu in emulators:
            item = QListWidgetItem(emu.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # 之前选中的恢复勾选
            if emu.name in old_selected:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)

            # 状态图标（左侧）
            icon = self.running_icon if emu.is_running() else self.stopped_icon
            item.setIcon(icon)

            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)
        # 更新当前选中集合
        self.selected_emulators = {item.text() for item in self.iter_checked_items()}

    def iter_checked_items(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                yield item

    def select_all(self):
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Checked)
        self.list_widget.blockSignals(False)
        self.selected_emulators = {item.text() for item in self.iter_checked_items()}

    def deselect_all(self):
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Unchecked)
        self.list_widget.blockSignals(False)
        self.selected_emulators.clear()

    def handle_item_changed(self, item):
        if item.checkState() == Qt.Checked:
            self.selected_emulators.add(item.text())
        else:
            self.selected_emulators.discard(item.text())

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
                log_util.log.print(f"{emulator.name}未运行，跳过执行")
                continue
            emulator_executor: EmulatorExecutor = EmulatorExecutor(config_manager.ADB_PATH,
                                                                   emulator.name,
                                                                   emulator.device_name)
            task_executor: TaskExecutor = TaskExecutor(emulator_executor=emulator_executor)
            task_config_name = self.config_name_combo.currentText().strip()
            task_config = self.task_config_manager.load_config_from_file(task_config_name)
            task_executor.execute_task_config(task_config)
        self.status_label.setText("✔️ 任务完成")

    def toggle_execution(self):
        if not self.is_running:
            if not self.selected_emulators:
                self.status_label.setText("⚠️ 请先选择要执行的模拟器")
                return
            self.start_tasks()
        else:
            self.stop_tasks()

    def start_tasks(self):
        self.is_running = True
        self.start_button.setText("停止执行")
        self.status_label.setText("▶️ 正在执行任务...")

        task_config_name = self.config_name_combo.currentText().strip()
        task_config = self.task_config_manager.load_config_from_file(task_config_name)

        for name in self.selected_emulators:
            emulator = next((e for e in self.manager.get_all_emulators() if e.name == name), None)
            if not emulator:
                continue
            thread = TaskThread(emulator, task_config, config_manager.ADB_PATH)
            thread.log_signal.connect(log_util.log.print)
            thread.finished_signal.connect(self.thread_finished)
            self.threads[name] = thread
            thread.start()

    def stop_tasks(self):
        self.status_label.setText("⏹️ 正在停止任务...")
        self.start_button.setText("开始执行")
        self.is_running = False

        for name, thread in self.threads.items():
            thread.stop()
        self.threads.clear()

    def thread_finished(self, name):
        log_util.log.print(f"🛑 {name} 线程已停止")
        self.threads.pop(name, None)

        if not self.threads:
            self.status_label.setText("✅ 所有任务线程已完成")
            self.start_button.setText("开始执行")
            self.is_running = False

    def get_selected_emulators(self):
        return list(self.selected_emulators)
