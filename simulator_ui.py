from PyQt5.QtWidgets import (
    QWidget, QListWidget, QPushButton, QHBoxLayout, QVBoxLayout,
    QListWidgetItem, QLabel
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor

import config_manager
from simulator_manager import EmulatorManager
from executor import EmulatorExecutor


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
        self.resize(600, 400)

        self.config_mgr = config_mgr

        self.manager = EmulatorManager(config_mgr.get("adb_path", config_manager.ADB_PATH),
                                       config_mgr.get("ldconsole_path", config_manager.LDCONSOLE_PATH))
        self.status_icon_size = self.config_mgr.get("status_icon_size", 12)
        self.running_icon = create_status_icon("green", self.status_icon_size)
        self.stopped_icon = create_status_icon("gray", self.status_icon_size)

        self.selected_emulators = set(self.config_mgr.get_selected_emulators())

        # UI 部件
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)

        self.select_all_button = QPushButton("全选")
        self.deselect_all_button = QPushButton("全不选")
        self.start_button = QPushButton("开始执行")
        self.status_label = QLabel("状态：空闲")

        # 布局
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.select_all_button)
        btn_layout.addWidget(self.deselect_all_button)
        btn_layout.addStretch()
        btn_layout.addWidget(self.start_button)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.list_widget)
        main_layout.addLayout(btn_layout)
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)

        # 连接信号槽
        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button.clicked.connect(self.deselect_all)
        self.start_button.clicked.connect(self.start_execution)
        self.list_widget.itemChanged.connect(self.handle_item_changed)

        # 定时刷新模拟器状态
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_emulators)
        self.timer.start(5000)  # 5秒刷新一次

        self.refresh_emulators()

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
                print(f"{emulator.name}未运行，跳过执行")
                continue

            executor = EmulatorExecutor(adb_path=self.manager.adb_path,
                                        name=emulator.name,
                                        device_name=emulator.device_name)
            success = executor.find_and_click_button()

            if success:
                print(f"✅ [{name}] 操作完成")
            else:
                print(f"❌ [{name}] 未完成点击")

        self.status_label.setText("✔️ 任务完成")

    def get_selected_emulators(self):
        return list(self.selected_emulators)
