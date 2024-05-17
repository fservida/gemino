from PySide6 import QtWidgets


class LoadingDialog(QtWidgets.QDialog):
    def __init__(self, title="Loading", label="Collecting File Information"):
        super().__init__()
        self.setWindowTitle(title)
        self.label = QtWidgets.QLabel(label)
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)
