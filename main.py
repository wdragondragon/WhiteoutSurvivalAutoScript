# main.py
import sys

from PyQt5.QtWidgets import QApplication

from config_manager import ConfigManager
from simulator_ui import EmulatorSelector
from utils import step_defined
from task_executor import TaskExecutor

if __name__ == '__main__':
    config_mgr = ConfigManager("config.json")

    # 自动加载所有任务
    TaskExecutor.load_all_tasks()

    # 1. 自动加载所有 YAML 任务
    step_defined.load_yaml_tasks()

    app = QApplication(sys.argv)
    win = EmulatorSelector(config_mgr)
    win.show()


    def on_exit():
        config_mgr.set_selected_emulators(win.get_selected_emulators())
        config_mgr.save()


    app.aboutToQuit.connect(on_exit)
    sys.exit(app.exec_())
