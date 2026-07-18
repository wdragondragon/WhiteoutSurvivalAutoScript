# simulator_ui.py
import os
import re
import subprocess

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtWidgets import (
    QWidget, QListWidget, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QComboBox, QTabWidget, QTextEdit, QTableWidget, QHeaderView, QCheckBox,
    QFormLayout, QSpinBox, QDoubleSpinBox, QTableWidgetItem, QLineEdit, QFileDialog
)

import log_util
from TaskConfigEditor import TaskConfigEditor
from component.EmulatorCellWidget import EmulatorCellWidget
from component.EmulatorComboBoxWidget import EmulatorComboBoxWidget
from config_manager import TaskConfigManager, ADB_PATH, LDCONSOLE_PATH, ConfigManager
from execution_scheduler import BatchExecutionThread
from input_synchronizer import InputSynchronizerThread, ReplaySynchronizerThread
from log_util import Log
from simulator_manager import EmulatorManager


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
    log_pyqt_signal = pyqtSignal(str)

    def __init__(self, config_mgr: ConfigManager):
        super().__init__()
        self.setWindowTitle("模拟器选择器")
        self.resize(800, 400)
        log_util.log = Log(self.log_pyqt_signal)
        self.scheduler_thread: BatchExecutionThread = None
        self.sync_thread: InputSynchronizerThread = None
        self.replay_thread: ReplaySynchronizerThread = None
        self.sync_recorded_actions = []
        self.is_running = False
        self.current_task_status_by_emulator = {}
        self._last_adb_refresh_warning = ""
        self.config_mgr: ConfigManager = config_mgr
        self.task_config_manager: TaskConfigManager = TaskConfigManager()

        self.manager: EmulatorManager = EmulatorManager(config_mgr.get("adb_path", ADB_PATH),
                                                        config_mgr.get("ldconsole_path", LDCONSOLE_PATH))
        self.status_icon_size = self.config_mgr.get("status_icon_size", 12)
        self.running_icon = create_status_icon("green", self.status_icon_size)
        self.stopped_icon = create_status_icon("gray", self.status_icon_size)

        self.selected_emulators = set(self.config_mgr.get_selected_emulators())

        # UI 部件
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)

        self.task_config_editor = TaskConfigEditor()

        self.select_all_button = QPushButton("全选")
        self.deselect_all_button = QPushButton("全不选")
        self.start_button = QPushButton("开始执行")
        self.start_emulator_button = QPushButton("启动模拟器")
        self.stop_emulator_button = QPushButton("关闭模拟器")
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
        btn_layout.addWidget(self.start_emulator_button)
        btn_layout.addWidget(self.stop_emulator_button)

        self.config_layout = QVBoxLayout()
        self.config_layout.addWidget(self.task_config_editor)
        self.config_save_layout = QHBoxLayout()
        self.config_save_layout.addWidget(self.config_name_combo)
        self.config_save_layout.addWidget(self.save_button)
        self.config_layout.addLayout(self.config_save_layout)
        self.config_tab = QWidget()
        self.config_tab.setLayout(self.config_layout)

        self.log_text = QTextEdit()
        self.log_text.document().setMaximumBlockCount(1000)
        self.log_text.setReadOnly(True)
        self.log_pyqt_signal.connect(self.append_log_text)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["模拟器", "绑定配置", "当前任务"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_layout = QVBoxLayout()
        self.table_layout.addWidget(self.table)
        self.table_layout.addLayout(btn_layout)
        self.table_layout.addWidget(self.status_label)

        self.emulator_table_tab = QWidget()
        self.emulator_table_tab.setLayout(self.table_layout)

        self.emulator_path_tab = self._create_emulator_path_tab()
        self.execution_settings_tab = self._create_execution_settings_tab()
        self.synchronizer_tab = self._create_synchronizer_tab()

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.emulator_table_tab, "模拟器列表")
        self.tab_widget.addTab(self.config_tab, "配置")
        self.tab_widget.addTab(self.emulator_path_tab, "模拟器路径")
        self.tab_widget.addTab(self.execution_settings_tab, "执行设置")
        self.tab_widget.addTab(self.synchronizer_tab, "同步器")
        self.tab_widget.addTab(self.log_text, "日志")

        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

        # 连接信号槽
        self.select_all_button.clicked.connect(lambda: self.select_all(True))
        self.deselect_all_button.clicked.connect(lambda: self.select_all(False))
        self.start_button.clicked.connect(self.toggle_execution)
        self.start_emulator_button.clicked.connect(self.start_selected_emulators)
        self.stop_emulator_button.clicked.connect(self.stop_selected_emulators)

        # 定时刷新模拟器状态
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_emulators)
        self.timer.start(5000)  # 5秒刷新一次

        # self.refresh_emulators()
        self.refresh_emulators()
        self.refresh_config_file_list()
        self.load_config_from_file(self.config_name_combo.currentText())
        self.load_emulator_paths()
        self.load_execution_settings()
        self.load_synchronizer_settings()
        self.refresh_sync_master_options()

    def append_log_text(self, msg):
        self.log_text.append(str(msg))
        self.log_text.ensureCursorVisible()

    def append_log_direct(self, msg):
        self.append_log_text(msg)
        print(msg, flush=True)

    def _create_path_picker(self, browse_handler):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        line_edit = QLineEdit()
        browse_button = QPushButton("选择")
        browse_button.clicked.connect(browse_handler)
        layout.addWidget(line_edit)
        layout.addWidget(browse_button)
        return container, line_edit

    def _create_emulator_path_tab(self):
        tab = QWidget()
        layout = QFormLayout()

        ldconsole_picker, self.ldconsole_path_edit = self._create_path_picker(self.browse_ldconsole_path)
        adb_picker, self.adb_path_edit = self._create_path_picker(self.browse_adb_path)
        self.ldconsole_path_edit.setPlaceholderText(r"例如: E:\leidian\LDPlayer9\ldconsole.exe")
        self.adb_path_edit.setPlaceholderText(r"例如: E:\leidian\LDPlayer9\adb.exe")
        self.pick_ldplayer_dir_button = QPushButton("选择雷电安装目录并自动填充")
        self.pick_ldplayer_dir_button.clicked.connect(self.browse_ldplayer_dir)
        self.save_emulator_path_button = QPushButton("保存并刷新模拟器列表")
        self.save_emulator_path_button.clicked.connect(self.save_emulator_paths)

        self.ldconsole_path_edit.editingFinished.connect(self.save_emulator_paths)
        self.adb_path_edit.editingFinished.connect(self.save_emulator_paths)

        layout.addRow("ldconsole.exe", ldconsole_picker)
        layout.addRow("adb.exe", adb_picker)
        layout.addRow("", self.pick_ldplayer_dir_button)
        layout.addRow("", self.save_emulator_path_button)

        tab.setLayout(layout)
        return tab

    def _create_execution_settings_tab(self):
        tab = QWidget()
        layout = QFormLayout()

        self.batch_enabled_checkbox = QCheckBox()
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 99)

        self.serial_actions_enabled_checkbox = QCheckBox()
        self.serial_interval_spin = QDoubleSpinBox()
        self.serial_interval_spin.setRange(0.0, 60.0)
        self.serial_interval_spin.setDecimals(2)
        self.serial_interval_spin.setSingleStep(0.1)

        self.relogin_interval_spin = QDoubleSpinBox()
        self.relogin_interval_spin.setRange(0.0, 600.0)
        self.relogin_interval_spin.setDecimals(1)
        self.relogin_interval_spin.setSingleStep(1.0)

        self.batch_start_timeout_spin = QSpinBox()
        self.batch_start_timeout_spin.setRange(1, 3600)

        self.batch_launch_interval_spin = QDoubleSpinBox()
        self.batch_launch_interval_spin.setRange(0.0, 600.0)
        self.batch_launch_interval_spin.setDecimals(1)
        self.batch_launch_interval_spin.setSingleStep(1.0)

        self.batch_between_delay_spin = QDoubleSpinBox()
        self.batch_between_delay_spin.setRange(0.0, 600.0)
        self.batch_between_delay_spin.setDecimals(1)
        self.batch_between_delay_spin.setSingleStep(1.0)

        layout.addRow("启用分批执行", self.batch_enabled_checkbox)
        layout.addRow("每批多开数量", self.batch_size_spin)
        layout.addRow("启用模拟器间串行操作", self.serial_actions_enabled_checkbox)
        layout.addRow("操作间隔/秒", self.serial_interval_spin)
        layout.addRow("被顶号重登等待/秒", self.relogin_interval_spin)
        layout.addRow("批次启动超时/秒", self.batch_start_timeout_spin)
        layout.addRow("上号间隔/秒", self.batch_launch_interval_spin)
        layout.addRow("批次间隔/秒", self.batch_between_delay_spin)

        for widget in (
                self.batch_enabled_checkbox,
                self.serial_actions_enabled_checkbox,
        ):
            widget.stateChanged.connect(self.save_execution_settings)
        for widget in (
                self.batch_size_spin,
                self.serial_interval_spin,
                self.relogin_interval_spin,
                self.batch_start_timeout_spin,
                self.batch_launch_interval_spin,
                self.batch_between_delay_spin,
        ):
            widget.valueChanged.connect(self.save_execution_settings)

        tab.setLayout(layout)
        return tab

    def _create_synchronizer_tab(self):
        tab = QWidget()
        layout = QFormLayout()

        self.sync_master_combo = QComboBox()
        self.sync_refresh_button = QPushButton("刷新主模拟器列表")
        self.sync_refresh_button.clicked.connect(self.refresh_sync_master_options)

        self.sync_delay_min_spin = QDoubleSpinBox()
        self.sync_delay_min_spin.setRange(0.0, 60.0)
        self.sync_delay_min_spin.setDecimals(2)
        self.sync_delay_min_spin.setSingleStep(0.1)

        self.sync_delay_max_spin = QDoubleSpinBox()
        self.sync_delay_max_spin.setRange(0.0, 60.0)
        self.sync_delay_max_spin.setDecimals(2)
        self.sync_delay_max_spin.setSingleStep(0.1)

        self.sync_random_offset_min_spin = QSpinBox()
        self.sync_random_offset_min_spin.setRange(0, 200)

        self.sync_random_offset_max_spin = QSpinBox()
        self.sync_random_offset_max_spin.setRange(0, 200)

        self.sync_delayed_replay_checkbox = QCheckBox("延后重放")
        self.sync_delayed_replay_checkbox.stateChanged.connect(self.on_delayed_replay_changed)

        self.sync_start_button = QPushButton("开始同步")
        self.sync_start_button.clicked.connect(self.toggle_synchronizer)

        self.sync_replay_button = QPushButton("重放录制")
        self.sync_replay_button.clicked.connect(self.toggle_replay)
        self.sync_replay_button.setEnabled(False)

        layout.addRow("主模拟器", self.sync_master_combo)
        layout.addRow("", self.sync_refresh_button)
        layout.addRow("最小延迟/秒", self.sync_delay_min_spin)
        layout.addRow("最大延迟/秒", self.sync_delay_max_spin)
        layout.addRow("坐标最小偏移/像素", self.sync_random_offset_min_spin)
        layout.addRow("坐标最大偏移/像素", self.sync_random_offset_max_spin)
        layout.addRow("", self.sync_delayed_replay_checkbox)
        layout.addRow("", self.sync_start_button)
        layout.addRow("", self.sync_replay_button)

        for widget in (
                self.sync_delay_min_spin,
                self.sync_delay_max_spin,
                self.sync_random_offset_min_spin,
                self.sync_random_offset_max_spin,
        ):
            widget.valueChanged.connect(self.save_synchronizer_settings)
        self.sync_master_combo.currentTextChanged.connect(self.save_synchronizer_settings)

        tab.setLayout(layout)
        return tab

    def load_synchronizer_settings(self):
        widgets = [
            self.sync_master_combo,
            self.sync_delay_min_spin,
            self.sync_delay_max_spin,
            self.sync_random_offset_min_spin,
            self.sync_random_offset_max_spin,
            self.sync_delayed_replay_checkbox,
        ]
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.sync_delay_min_spin.setValue(float(self.config_mgr.get("sync_delay_min_sec", 0.0) or 0.0))
            self.sync_delay_max_spin.setValue(float(self.config_mgr.get("sync_delay_max_sec", 0.0) or 0.0))
            legacy_offset = int(self.config_mgr.get("sync_random_offset_px", 0) or 0)
            offset_min = int(self.config_mgr.get("sync_random_offset_min_px", 0) or 0)
            offset_max = int(self.config_mgr.get("sync_random_offset_max_px", legacy_offset) or 0)
            self.sync_random_offset_min_spin.setValue(min(offset_min, offset_max))
            self.sync_random_offset_max_spin.setValue(max(offset_min, offset_max))
            self.sync_delayed_replay_checkbox.setChecked(bool(self.config_mgr.get("sync_delayed_replay_enabled", False)))
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self.update_synchronizer_controls()

    def save_synchronizer_settings(self):
        if not hasattr(self, "sync_delay_min_spin"):
            return
        delay_min = min(self.sync_delay_min_spin.value(), self.sync_delay_max_spin.value())
        delay_max = max(self.sync_delay_min_spin.value(), self.sync_delay_max_spin.value())
        offset_min = min(self.sync_random_offset_min_spin.value(), self.sync_random_offset_max_spin.value())
        offset_max = max(self.sync_random_offset_min_spin.value(), self.sync_random_offset_max_spin.value())
        self.config_mgr.set("sync_master_name", self.sync_master_combo.currentText().strip())
        self.config_mgr.set("sync_delay_min_sec", delay_min)
        self.config_mgr.set("sync_delay_max_sec", delay_max)
        self.config_mgr.set("sync_random_offset_min_px", offset_min)
        self.config_mgr.set("sync_random_offset_max_px", offset_max)
        self.config_mgr.set("sync_random_offset_px", offset_max)
        self.config_mgr.set("sync_delayed_replay_enabled", self.sync_delayed_replay_checkbox.isChecked())
        self.config_mgr.save()

    def on_delayed_replay_changed(self, _state=None):
        self.save_synchronizer_settings()
        self.update_synchronizer_controls()

    def update_synchronizer_controls(self):
        if not hasattr(self, "sync_start_button"):
            return
        delayed = self.sync_delayed_replay_checkbox.isChecked()
        if self.sync_thread:
            self.sync_start_button.setText("停止录制" if delayed else "停止同步")
        else:
            self.sync_start_button.setText("开始录制" if delayed else "开始同步")
        if self.replay_thread:
            self.sync_replay_button.setText("停止重放")
            self.sync_replay_button.setEnabled(True)
        else:
            self.sync_replay_button.setText("重放录制")
            self.sync_replay_button.setEnabled(delayed and bool(self.sync_recorded_actions) and not self.sync_thread)

    def refresh_sync_master_options(self):
        if not hasattr(self, "sync_master_combo"):
            return
        selected_names = self.get_selected_emulator_names_in_table_order()
        current = self.sync_master_combo.currentText().strip() or self.config_mgr.get("sync_master_name", "")
        self.sync_master_combo.blockSignals(True)
        try:
            self.sync_master_combo.clear()
            self.sync_master_combo.addItems(selected_names)
            if current in selected_names:
                self.sync_master_combo.setCurrentText(current)
        finally:
            self.sync_master_combo.blockSignals(False)

    def load_emulator_paths(self):
        widgets = [self.ldconsole_path_edit, self.adb_path_edit]
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.ldconsole_path_edit.setText(self.config_mgr.get("ldconsole_path", LDCONSOLE_PATH))
            self.adb_path_edit.setText(self.config_mgr.get("adb_path", ADB_PATH))
        finally:
            for widget in widgets:
                widget.blockSignals(False)

    def browse_ldconsole_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 ldconsole.exe",
            self.ldconsole_path_edit.text().strip() or LDCONSOLE_PATH,
            "可执行文件 (*.exe);;所有文件 (*.*)",
        )
        if path:
            self.ldconsole_path_edit.setText(path)
            self.save_emulator_paths()

    def browse_adb_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 adb.exe",
            self.adb_path_edit.text().strip() or ADB_PATH,
            "可执行文件 (*.exe);;所有文件 (*.*)",
        )
        if path:
            self.adb_path_edit.setText(path)
            self.save_emulator_paths()

    def browse_ldplayer_dir(self):
        current_path = self.ldconsole_path_edit.text().strip() or LDCONSOLE_PATH
        current_dir = os.path.dirname(current_path) if current_path else ""
        directory = QFileDialog.getExistingDirectory(self, "选择雷电模拟器安装目录", current_dir)
        if not directory:
            return

        ldconsole_path = os.path.join(directory, "ldconsole.exe")
        adb_path = os.path.join(directory, "adb.exe")
        self.ldconsole_path_edit.setText(ldconsole_path)
        self.adb_path_edit.setText(adb_path)
        self.save_emulator_paths()

    def save_emulator_paths(self):
        if not hasattr(self, "ldconsole_path_edit"):
            return
        if self.is_running:
            self.status_label.setText("正在执行任务，暂不能修改模拟器路径")
            self.load_emulator_paths()
            return

        ldconsole_path = self.ldconsole_path_edit.text().strip()
        adb_path = self.adb_path_edit.text().strip()
        if not ldconsole_path:
            ldconsole_path = LDCONSOLE_PATH
            self.ldconsole_path_edit.setText(ldconsole_path)
        if not adb_path:
            adb_path = ADB_PATH
            self.adb_path_edit.setText(adb_path)

        missing_paths = []
        if not os.path.isfile(ldconsole_path):
            missing_paths.append(f"ldconsole.exe: {ldconsole_path}")
        if not os.path.isfile(adb_path):
            missing_paths.append(f"adb.exe: {adb_path}")
        if missing_paths:
            message = "模拟器路径不存在，请重新选择: " + "；".join(missing_paths)
            self.status_label.setText(message)
            log_util.log.print(message)
            return

        self.config_mgr.set("ldconsole_path", ldconsole_path)
        self.config_mgr.set("adb_path", adb_path)
        self.config_mgr.save()
        self.manager = EmulatorManager(adb_path, ldconsole_path)
        self.status_label.setText("模拟器路径已保存")
        log_util.log.print(f"模拟器路径已保存: ldconsole={ldconsole_path}, adb={adb_path}")
        self.refresh_emulators()

    def load_execution_settings(self):
        settings = self.config_mgr.get_execution_settings()
        widgets = [
            self.batch_enabled_checkbox,
            self.batch_size_spin,
            self.serial_actions_enabled_checkbox,
            self.serial_interval_spin,
            self.relogin_interval_spin,
            self.batch_start_timeout_spin,
            self.batch_launch_interval_spin,
            self.batch_between_delay_spin,
        ]
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.batch_enabled_checkbox.setChecked(settings["batch_enabled"])
            self.batch_size_spin.setValue(settings["batch_size"])
            self.serial_actions_enabled_checkbox.setChecked(settings["serial_actions_enabled"])
            self.serial_interval_spin.setValue(settings["serial_action_interval_sec"])
            self.relogin_interval_spin.setValue(settings["relogin_interval_sec"])
            self.batch_start_timeout_spin.setValue(settings["batch_start_timeout_sec"])
            self.batch_launch_interval_spin.setValue(settings["batch_launch_interval_sec"])
            self.batch_between_delay_spin.setValue(settings["batch_between_delay_sec"])
        finally:
            for widget in widgets:
                widget.blockSignals(False)

    def get_execution_settings_from_ui(self):
        return {
            "batch_enabled": self.batch_enabled_checkbox.isChecked(),
            "batch_size": self.batch_size_spin.value(),
            "batch_cycle_mode": "loop",
            "serial_actions_enabled": self.serial_actions_enabled_checkbox.isChecked(),
            "serial_action_interval_sec": self.serial_interval_spin.value(),
            "relogin_interval_sec": self.relogin_interval_spin.value(),
            "batch_start_timeout_sec": self.batch_start_timeout_spin.value(),
            "batch_launch_interval_sec": self.batch_launch_interval_spin.value(),
            "batch_between_delay_sec": self.batch_between_delay_spin.value(),
        }

    def save_execution_settings(self):
        if not hasattr(self, "batch_enabled_checkbox"):
            return
        self.config_mgr.set_execution_settings(self.get_execution_settings_from_ui())

    def load_config_from_file(self, config_name):
        if config_name:
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
        self.refresh_config_file_list()

    def _current_emulator_row_names(self):
        names = []
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if isinstance(widget, EmulatorCellWidget):
                names.append(widget.get_name())
        return names

    def _restore_table_scroll(self, vertical_value, horizontal_value):
        vertical_bar = self.table.verticalScrollBar()
        horizontal_bar = self.table.horizontalScrollBar()
        vertical_bar.setValue(min(vertical_value, vertical_bar.maximum()))
        horizontal_bar.setValue(min(horizontal_value, horizontal_bar.maximum()))

    def _rebuild_emulator_table(self, emulators, selected_names):
        config_names = self.task_config_manager.get_config_name_list()
        self.table.setRowCount(0)

        for row, emu in enumerate(emulators):
            self.table.insertRow(row)

            emulator_item = EmulatorCellWidget(name=emu.name,
                                               is_running=emu.is_running(),
                                               running_icon=self.running_icon,
                                               stopped_icon=self.stopped_icon,
                                               is_checked=emu.name in selected_names)

            emulator_item.checkedChanged.connect(self.on_emulator_checkbox_changed)

            cur_config_name = self.config_mgr.get_emulator_bindings(emulator_name=emu.name)
            config_combo_item = EmulatorComboBoxWidget(name=emu.name,
                                                       items=config_names,
                                                       current=cur_config_name)
            config_combo_item.currentTextChanged.connect(self.on_bind_config_combo_changed)

            self.table.setCellWidget(row, 0, emulator_item)
            self.table.setCellWidget(row, 1, config_combo_item)
            current_task_item = QTableWidgetItem(self.current_task_status_by_emulator.get(emu.name, ""))
            current_task_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, current_task_item)

        self.update_selected_emulators()

    def refresh_emulators(self):
        try:
            emulators = self.manager.get_all_emulators()
        except Exception as e:
            message = f"刷新模拟器列表失败，请检查雷电模拟器路径配置: {e}"
            self.status_label.setText(message)
            log_util.log.print(message)
            return
        adb_detail = getattr(self.manager, "last_adb_connect_detail", "")
        if adb_detail.startswith("获取 ADB 设备列表失败"):
            self.status_label.setText("模拟器列表已刷新，但 ADB 设备状态获取失败；运行状态可能不完整")
            if adb_detail != self._last_adb_refresh_warning:
                log_util.log.print(adb_detail)
                self._last_adb_refresh_warning = adb_detail
        else:
            self._last_adb_refresh_warning = ""
        selected_names = self.selected_emulators.copy()
        emulator_names = [emu.name for emu in emulators]
        current_names = self._current_emulator_row_names()
        vertical_value = self.table.verticalScrollBar().value()
        horizontal_value = self.table.horizontalScrollBar().value()

        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            if current_names != emulator_names:
                self._rebuild_emulator_table(emulators, selected_names)
            else:
                for row, emu in enumerate(emulators):
                    widget = self.table.cellWidget(row, 0)
                    if isinstance(widget, EmulatorCellWidget):
                        widget.set_status(emu.is_running())
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
            self._restore_table_scroll(vertical_value, horizontal_value)
            QTimer.singleShot(0, lambda: self._restore_table_scroll(vertical_value, horizontal_value))
            self.refresh_sync_master_options()

    def update_selected_emulators(self):
        self.selected_emulators.clear()
        for row in range(self.table.rowCount()):
            table_item: EmulatorCellWidget = self.table.cellWidget(row, 0)
            if table_item and table_item.is_checked():
                name = table_item.get_name()
                if name:
                    self.selected_emulators.add(name)

    def on_emulator_checkbox_changed(self, name: str, checked: bool):
        if checked:
            self.selected_emulators.add(name)
        else:
            self.selected_emulators.discard(name)
        log_util.log.print(f"当前选中: {','.join(self.selected_emulators)}")
        self.refresh_sync_master_options()

    def on_bind_config_combo_changed(self, emu_name: str, config_name: str):
        log_util.log.print(f"配置绑定[{emu_name}]->[{config_name}]")
        self.config_mgr.set_emulator_bindings(emu_name, config_name)

    def update_current_task_status(self, emulator_name: str, task_name: str):
        self.current_task_status_by_emulator[emulator_name] = task_name or ""
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if not isinstance(widget, EmulatorCellWidget) or widget.get_name() != emulator_name:
                continue
            item = self.table.item(row, 2)
            if item is None:
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 2, item)
            item.setText(task_name or "")
            break

    def iter_checked_items(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                yield item

    def select_all(self, checked: bool):
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if isinstance(widget, EmulatorCellWidget):
                widget.set_checked(checked)
        if checked:
            self.selected_emulators = self.get_selected_emulator_names()
        else:
            self.selected_emulators.clear()
        self.refresh_sync_master_options()

    def get_selected_emulator_names(self) -> set:
        selected_names = set()
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if isinstance(widget, EmulatorCellWidget) and widget.is_checked():
                selected_names.add(widget.get_name())
        return selected_names

    def get_selected_emulator_names_in_table_order(self):
        selected_names = []
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if isinstance(widget, EmulatorCellWidget) and widget.is_checked():
                selected_names.append(widget.get_name())
        return selected_names

    def start_selected_emulators(self):
        selected_names = self.get_selected_emulator_names_in_table_order()
        if not selected_names:
            self.status_label.setText("请先选择要启动的模拟器")
            return

        emulators = {emu.name: emu for emu in self.manager.get_all_emulators()}
        started_count = 0
        for name in selected_names:
            emulator = emulators.get(name)
            if not emulator:
                log_util.log.print(f"[启动模拟器] 未找到 {name}")
                continue
            if emulator.is_running():
                log_util.log.print(f"[启动模拟器] {name} 已在运行，跳过")
                continue
            if self.manager.start_emulator(emulator.index):
                started_count += 1
                log_util.log.print(f"[启动模拟器] 已发送启动命令: {name}")
            else:
                log_util.log.print(f"[启动模拟器] 启动失败: {name}")

        self.status_label.setText(f"已发送启动命令：{started_count} 个模拟器")
        QTimer.singleShot(2000, self.refresh_emulators)
        QTimer.singleShot(6000, self.refresh_emulators)

    def stop_selected_emulators(self):
        selected_names = self.get_selected_emulator_names_in_table_order()
        if not selected_names:
            self.status_label.setText("请先选择要关闭的模拟器")
            return

        emulators = {emu.name: emu for emu in self.manager.get_all_emulators()}
        stopped_count = 0
        for name in selected_names:
            emulator = emulators.get(name)
            if not emulator:
                log_util.log.print(f"[关闭模拟器] 未找到 {name}")
                continue
            if not emulator.is_running():
                log_util.log.print(f"[关闭模拟器] {name} 未运行，跳过")
                continue
            if self.manager.stop_emulator(emulator.index):
                stopped_count += 1
                log_util.log.print(f"[关闭模拟器] 已发送关闭命令: {name}")
            else:
                log_util.log.print(f"[关闭模拟器] 关闭失败: {name}")

        self.status_label.setText(f"已发送关闭命令：{stopped_count} 个模拟器")
        QTimer.singleShot(1000, self.refresh_emulators)
        QTimer.singleShot(3000, self.refresh_emulators)

    def toggle_synchronizer(self):
        if self.sync_thread:
            self.stop_synchronizer()
        else:
            self.start_synchronizer()

    def start_synchronizer(self):
        if self.is_running:
            self.status_label.setText("正在执行任务，请先停止任务再启动同步器")
            return
        if self.replay_thread:
            self.status_label.setText("正在重放录制，请先停止重放")
            return

        selected_names = self.get_selected_emulator_names_in_table_order()
        if len(selected_names) < 2:
            self.status_label.setText("同步器至少需要勾选 2 个运行中的模拟器")
            return

        self.refresh_sync_master_options()
        master_name = self.sync_master_combo.currentText().strip()
        if not master_name or master_name not in selected_names:
            self.status_label.setText("请选择一个已勾选的主模拟器")
            return

        try:
            emulators = {emu.name: emu for emu in self.manager.get_all_emulators()}
        except Exception as e:
            self.status_label.setText(f"启动同步器失败，无法刷新模拟器列表: {e}")
            return

        targets = {}
        for name in selected_names:
            emulator = emulators.get(name)
            target = self._build_sync_target(emulator)
            if not target:
                self.status_label.setText(f"启动同步器失败，{name} 未运行或 ADB 未就绪")
                return
            targets[name] = target

        master = targets[master_name]
        followers = [target for name, target in targets.items() if name != master_name]
        if not followers:
            self.status_label.setText("同步器没有从模拟器")
            return

        delay_min = min(self.sync_delay_min_spin.value(), self.sync_delay_max_spin.value())
        delay_max = max(self.sync_delay_min_spin.value(), self.sync_delay_max_spin.value())
        offset_min = min(self.sync_random_offset_min_spin.value(), self.sync_random_offset_max_spin.value())
        offset_max = max(self.sync_random_offset_min_spin.value(), self.sync_random_offset_max_spin.value())
        execution_settings = self.config_mgr.get_execution_settings()
        serial_interval = (
            execution_settings["serial_action_interval_sec"]
            if execution_settings["serial_actions_enabled"]
            else 0.0
        )
        record_only = self.sync_delayed_replay_checkbox.isChecked()
        if record_only:
            self.sync_recorded_actions = []
        self.sync_thread = InputSynchronizerThread(
            adb_path=self.config_mgr.get("adb_path", ADB_PATH),
            master=master,
            followers=followers,
            delay_min_sec=delay_min,
            delay_max_sec=delay_max,
            random_offset_min_px=offset_min,
            random_offset_max_px=offset_max,
            record_only=record_only,
            serial_interval_sec=serial_interval,
        )
        self.sync_thread.log_signal.connect(self.append_log_direct)
        self.sync_thread.finished_signal.connect(self.synchronizer_finished)
        self.sync_thread.start()

        self.save_synchronizer_settings()
        self.update_synchronizer_controls()
        mode_text = "录制中" if record_only else "运行中"
        self.status_label.setText(f"同步器{mode_text}：主模拟器 {master_name}，从模拟器 {len(followers)} 个")
        log_util.log.print(f"同步器已启动: 模式={mode_text}, 主模拟器={master_name}, 从模拟器={len(followers)}")

    def _build_sync_target(self, emulator):
        if not emulator or not emulator.is_running():
            return None
        device_name = emulator.device_name
        if not device_name:
            device_name = self.manager.connect_adb_device(emulator.index)
        if not device_name:
            log_util.log.print(f"[同步器] {getattr(emulator, 'name', '')} ADB 未就绪: {self.manager.last_adb_connect_detail}")
            return None

        width, height = self._read_sync_screen_size(device_name, emulator.width, emulator.height)
        return {
            "name": emulator.name,
            "device_name": device_name,
            "width": width,
            "height": height,
        }

    def _read_sync_screen_size(self, device_name, fallback_width, fallback_height):
        try:
            result = subprocess.run(
                [self.config_mgr.get("adb_path", ADB_PATH), "-s", device_name, "shell", "wm", "size"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5,
            )
            output = (result.stdout + result.stderr).decode(errors="ignore")
            match = re.search(r"(\d+)\s*x\s*(\d+)", output)
            if match:
                return int(match.group(1)), int(match.group(2))
        except (OSError, subprocess.TimeoutExpired):
            pass

        width = int(fallback_width or 0)
        height = int(fallback_height or 0)
        if width > 0 and height > 0:
            return width, height
        return 450, 800

    def stop_synchronizer(self):
        self.status_label.setText("正在停止同步器...")
        if self.sync_thread:
            self.sync_thread.stop()

    def toggle_replay(self):
        if self.replay_thread:
            self.stop_replay()
        else:
            self.start_replay()

    def start_replay(self):
        if self.is_running:
            self.status_label.setText("正在执行任务，请先停止任务再重放录制")
            return
        if self.sync_thread:
            self.status_label.setText("正在录制或同步，请先停止后再重放")
            return
        if not self.sync_recorded_actions:
            self.status_label.setText("没有可重放的录制动作")
            return

        selected_names = self.get_selected_emulator_names_in_table_order()
        if len(selected_names) < 2:
            self.status_label.setText("重放至少需要勾选 2 个运行中的模拟器")
            return
        self.refresh_sync_master_options()
        master_name = self.sync_master_combo.currentText().strip()
        if not master_name or master_name not in selected_names:
            self.status_label.setText("请选择一个已勾选的主模拟器")
            return

        try:
            emulators = {emu.name: emu for emu in self.manager.get_all_emulators()}
        except Exception as e:
            self.status_label.setText(f"启动重放失败，无法刷新模拟器列表: {e}")
            return

        followers = []
        for name in selected_names:
            if name == master_name:
                continue
            target = self._build_sync_target(emulators.get(name))
            if not target:
                self.status_label.setText(f"启动重放失败，{name} 未运行或 ADB 未就绪")
                return
            followers.append(target)
        if not followers:
            self.status_label.setText("重放没有从模拟器")
            return

        delay_min = min(self.sync_delay_min_spin.value(), self.sync_delay_max_spin.value())
        delay_max = max(self.sync_delay_min_spin.value(), self.sync_delay_max_spin.value())
        offset_min = min(self.sync_random_offset_min_spin.value(), self.sync_random_offset_max_spin.value())
        offset_max = max(self.sync_random_offset_min_spin.value(), self.sync_random_offset_max_spin.value())
        execution_settings = self.config_mgr.get_execution_settings()
        serial_interval = (
            execution_settings["serial_action_interval_sec"]
            if execution_settings["serial_actions_enabled"]
            else 0.0
        )

        self.replay_thread = ReplaySynchronizerThread(
            adb_path=self.config_mgr.get("adb_path", ADB_PATH),
            followers=followers,
            recorded_actions=self.sync_recorded_actions,
            delay_min_sec=delay_min,
            delay_max_sec=delay_max,
            serial_interval_sec=serial_interval,
            random_offset_min_px=offset_min,
            random_offset_max_px=offset_max,
        )
        self.replay_thread.log_signal.connect(self.append_log_direct)
        self.replay_thread.finished_signal.connect(self.replay_finished)
        self.replay_thread.start()

        self.save_synchronizer_settings()
        self.update_synchronizer_controls()
        self.status_label.setText(f"正在重放录制：动作 {len(self.sync_recorded_actions)} 个，从模拟器 {len(followers)} 个")
        log_util.log.print(f"同步器开始重放录制: 动作={len(self.sync_recorded_actions)}, 从模拟器={len(followers)}")

    def stop_replay(self):
        self.status_label.setText("正在停止重放...")
        if self.replay_thread:
            self.replay_thread.stop()

    def replay_finished(self):
        log_util.log.print("同步器录制重放已结束")
        self.replay_thread = None
        self.update_synchronizer_controls()
        self.status_label.setText("录制重放已结束")

    def synchronizer_finished(self):
        was_recording = bool(self.sync_thread and getattr(self.sync_thread, "record_only", False))
        if was_recording:
            self.sync_recorded_actions = self.sync_thread.get_recorded_actions()
            log_util.log.print(f"同步器录制已停止，共录制 {len(self.sync_recorded_actions)} 个动作")
        else:
            log_util.log.print("同步器已停止")
        self.sync_thread = None
        self.update_synchronizer_controls()
        if was_recording:
            self.status_label.setText(f"录制已停止，共 {len(self.sync_recorded_actions)} 个动作")
        else:
            self.status_label.setText("同步器已停止")

    def toggle_execution(self):
        if self.sync_thread:
            self.status_label.setText("同步器运行中，请先停止同步器再执行任务")
            return
        if self.replay_thread:
            self.status_label.setText("同步器正在重放录制，请先停止重放再执行任务")
            return
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

        selected_names = self.get_selected_emulator_names_in_table_order()
        execution_settings = self.get_execution_settings_from_ui()
        self.config_mgr.set_execution_settings(execution_settings)

        task_configs = {}
        for name in selected_names:
            task_config_name = self.config_mgr.get_emulator_bindings(name)
            if not task_config_name and self.config_name_combo.size() != 0:
                task_config_name = self.config_name_combo.currentText()
            log_util.log.print(f"[调度{name}]->配置[{task_config_name}]")
            task_config = self.task_config_manager.load_config_from_file(task_config_name)
            task_configs[name] = task_config

        self.scheduler_thread = BatchExecutionThread(
            selected_names=selected_names,
            task_configs=task_configs,
            execution_settings=execution_settings,
            adb_path=self.config_mgr.get("adb_path", ADB_PATH),
            ldconsole_path=self.config_mgr.get("ldconsole_path", LDCONSOLE_PATH),
            fallback_config_name=self.config_name_combo.currentText(),
        )
        self.scheduler_thread.log_signal.connect(log_util.log.print)
        self.scheduler_thread.task_status_signal.connect(self.update_current_task_status)
        self.scheduler_thread.finished_signal.connect(self.scheduler_finished)
        self.scheduler_thread.start()

    def stop_tasks(self):
        self.status_label.setText("⏹️ 正在停止任务...")
        self.start_button.setText("开始执行")
        self.is_running = False
        if self.scheduler_thread:
            self.scheduler_thread.stop()

    def scheduler_finished(self):
        log_util.log.print("调度线程已停止")
        self.scheduler_thread = None
        for emulator_name in list(self.current_task_status_by_emulator):
            self.update_current_task_status(emulator_name, "")
        self.status_label.setText("所有任务线程已完成")
        self.start_button.setText("开始执行")
        self.is_running = False

    def get_selected_emulators(self):
        return list(self.selected_emulators)
