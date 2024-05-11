from PySide6 import QtWidgets


class LogDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget, title: str, log: str):
        super().__init__(parent=parent)
        self.__title = title
        self.__setup_ui()  # Must be after setting title and before the first call to log setter
        self.log = log
        self.resize(900, 500)

    def __setup_ui(self):
        self.setWindowTitle(self.__title)

        self.__log_text_field = QtWidgets.QTextEdit()
        self.__log_text_field.setReadOnly(True)

        self.__close_button = QtWidgets.QPushButton("Close")
        self.__close_button.clicked.connect(self.close)

        self.__layout_container = QtWidgets.QVBoxLayout()
        self.__layout_container.addWidget(self.__log_text_field)
        self.__layout_container.addWidget(self.__close_button)

        self.setLayout(self.__layout_container)

    def __update_log(self):
        self.__log_text_field.setText(self.__log)

    @property
    def log(self):
        return self.__log

    @log.setter
    def log(self, log):
        self.__log = log
        self.__update_log()