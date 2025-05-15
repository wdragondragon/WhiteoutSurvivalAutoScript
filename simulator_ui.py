# simulator_ui.py
from PyQt5.QtWidgets import (
    QWidget, QListWidget, QPushButton, QHBoxLayout, QVBoxLayout, QListWidgetItem, QLabel
)
from PyQt5.QtCore import QTimer, Qt

from executor import EmulatorExecutor
from simulator_manager import EmulatorManager

ADB_PATH = r"C:\leidian\LDPlayer9\adb.exe"
LDCONSOLE_PATH = r"C:\leidian\LDPlayer9\ldconsole.exe"


class EmulatorSelector(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("模拟器选择器")
        self.resize(600, 400)
        self.manager = EmulatorManager(ADB_PATH, LDCONSOLE_PATH)

        self.available_list = QListWidget()
        self.selected_list = QListWidget()

        self.add_button = QPushButton("→")
        self.remove_button = QPushButton("←")
        self.start_button = QPushButton("开始执行")

        button_layout = QVBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addStretch()

        main_layout = QHBoxLayout()
        main_layout.addWidget(QLabel("正在运行的模拟器"))
        main_layout.addWidget(QLabel("已选择的模拟器"))
        layout = QHBoxLayout()
        layout.addWidget(self.available_list)
        layout.addLayout(button_layout)
        layout.addWidget(self.selected_list)

        vlayout = QVBoxLayout()
        vlayout.addLayout(main_layout)
        vlayout.addLayout(layout)
        vlayout.addWidget(self.start_button)

        self.setLayout(vlayout)

        self.add_button.clicked.connect(self.add_selected)
        self.remove_button.clicked.connect(self.remove_selected)
        self.start_button.clicked.connect(self.start_execution)

        self.available_list.itemDoubleClicked.connect(self._on_add_double_click)
        self.selected_list.itemDoubleClicked.connect(self._on_remove_double_click)

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_emulators)
        self.timer.start(5000)

        self.refresh_emulators()

    def refresh_emulators(self):
        running = set(self.manager.get_running_emulators())
        for i in reversed(range(self.selected_list.count())):
            text = self.selected_list.item(i).text()
            if text not in running:
                self.selected_list.takeItem(i)
        self._refresh_available_list(running)

    def add_selected(self):
        for item in self.available_list.selectedItems():
            text = item.text()
            if not self.selected_list.findItems(text, Qt.MatchExactly):
                self.selected_list.addItem(text)
        self._refresh_available_list()

    def remove_selected(self):
        for item in self.selected_list.selectedItems():
            self.selected_list.takeItem(self.selected_list.row(item))
        self._refresh_available_list()

    def start_execution(self):
        selected = [self.selected_list.item(i).text() for i in range(self.selected_list.count())]
        if not selected:
            print("⚠️ 请先选择要执行的模拟器")
            return

        for name in selected:
            print(f"▶️ 开始处理模拟器：{name}")
            executor = EmulatorExecutor(self.manager.adb_path, name)
            success = executor.find_and_click_button()
            if success:
                print(f"✅ [{name}] 操作完成")
            else:
                print(f"❌ [{name}] 未完成点击")

    def _refresh_available_list(self, running=None):
        if running is None:
            running = set(self.manager.get_running_emulators())
        selected = set(self._get_all_items(self.selected_list))
        available = sorted(running - selected)

        self.available_list.clear()
        for emu in available:
            self.available_list.addItem(QListWidgetItem(emu))

    def _get_all_items(self, list_widget):
        return [list_widget.item(i).text() for i in range(list_widget.count())]

    def _on_add_double_click(self, item):
        text = item.text()
        if not self._list_has_item(self.selected_list, text):
            self.selected_list.addItem(text)
            self._refresh_available_list()

    def _on_remove_double_click(self, item):
        self.selected_list.takeItem(self.selected_list.row(item))
        self._refresh_available_list()

    def _list_has_item(self, list_widget, text):
        return any(list_widget.item(i).text() == text for i in range(list_widget.count()))
