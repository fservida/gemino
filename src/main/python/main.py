from PySide6.QtWidgets import QApplication

import sys

from gemino.widgets import MainWindow, ErrorWindow, error_box
from gemino.vars import VERSION


if __name__ == "__main__":
    exit_code = -1
    app = QApplication(sys.argv)
    try:
        window = MainWindow(VERSION)
        window.setWindowTitle("gemino v" + VERSION)
        window.resize(800, 600)
        window.show()
        exit_code = app.exec()
    except Exception as e:
        window = ErrorWindow(e)
        window.resize(800, 600)
        window.show()
        error_box(
            window, "Error", "An Error Occurred and the Application Crashed", str(e)
        )
        app.exec()
    sys.exit(exit_code)
