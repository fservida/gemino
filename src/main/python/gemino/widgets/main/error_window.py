from PySide6 import QtWidgets


class ErrorWindow(QtWidgets.QMainWindow):
    def __init__(self, error):
        super().__init__()