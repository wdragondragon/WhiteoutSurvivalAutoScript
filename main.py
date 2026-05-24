# main.py
import sys

from PyQt5.QtWidgets import QApplication

from config_manager import ConfigManager
from simulator_ui import EmulatorSelector
from utils import task_defined

if __name__ == '__main__':
    config_mgr = ConfigManager("config.json")

    # 自动加载所有任务
    task_defined.load_all_tasks()

    app = QApplication(sys.argv)
    win = EmulatorSelector(config_mgr)
    win.show()


    def on_exit():
        config_mgr.set_selected_emulators(win.get_selected_emulators())
        config_mgr.save()


    app.aboutToQuit.connect(on_exit)
    sys.exit(app.exec_())
