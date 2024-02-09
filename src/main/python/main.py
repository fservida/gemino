from PySide2.QtWidgets import QApplication

import sys

from gemino.widgets import MainWindow

VERSION = "2.7.0"

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow(VERSION)
    window.setWindowTitle("gemino v" + VERSION)
    window.resize(800, 600)
    window.show()
    exit_code = app.exec_()
    sys.exit(exit_code)
