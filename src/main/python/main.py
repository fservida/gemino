from PySide6.QtWidgets import QApplication
import traceback

import sys

from gemino.widgets.main import MainWindow, ErrorWindow
from gemino.widgets.common import error_box
from gemino.vars import VERSION


if __name__ == "__main__":
    exit_code = -1
    app = QApplication(sys.argv)
    try:
        window = MainWindow(VERSION)
        window.setWindowTitle("gemino v" + VERSION)
        window.resize(1000, 600)
        window.show()
        exit_code = app.exec()
    except Exception as e:
        window = ErrorWindow(e)
        window.resize(1000, 600)
        window.show()
        error_box(
            window,
            "Error",
            "An Error Occurred and the Application Crashed",
            traceback.format_exc(),
        )
        app.exec()
    sys.exit(exit_code)
