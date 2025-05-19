# main.py
import sys
from PyQt5.QtWidgets import QApplication
from simulator_ui import EmulatorSelector
from config_manager import ConfigManager

if __name__ == '__main__':
    config_mgr = ConfigManager("config.json")

    app = QApplication(sys.argv)
    win = EmulatorSelector(config_mgr)
    win.show()


    def on_exit():
        config_mgr.set_selected_emulators(win.get_selected_emulators())
        config_mgr.save()


    app.aboutToQuit.connect(on_exit)
    sys.exit(app.exec_())
