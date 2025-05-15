# main.py
import sys
from PyQt5.QtWidgets import QApplication
from simulator_ui import EmulatorSelector

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = EmulatorSelector()
    win.show()
    sys.exit(app.exec_())
