from PySide6 import QtWidgets, QtCore

from ...threads.common.threads import TaskThread
from ...threads.common.utils import ProgressData


class LoadingWindow(QtWidgets.QDialog):
    """
    Generic Class receiving an already instantiated thread
    Upon start, the class will monitor the thread "task_status" signal
    and will call "return_function" when the progress status received is 0
    passing the progress payload as kwargs to the function.

    All the while, if status is 1, it will update the interface as needed.
    """

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        total_items: int,
        call_thread: TaskThread,
        return_function,
    ):
        super().__init__(parent=parent)

        self.setWindowTitle("Parsing")
        self.__return_function = return_function

        self.__current_item = None
        self.__processed_items = 0
        self.__total_items = total_items

        self.__thread = call_thread
        self.__thread.task_progress.connect(
            self.update_progress, QtCore.Qt.QueuedConnection
        )

        self.__setup_ui()
        self.__update_ui()

    def __setup_ui(self):
        self.__layout = QtWidgets.QVBoxLayout()

        self.__status_label = QtWidgets.QLabel()
        self.__status_label.setText("Loading Container")
        self.__progress_bar = QtWidgets.QProgressBar()
        self.__progress_bar.setMaximum(0)
        # self.__current_item_label = QtWidgets.QLabel()
        self.__file_progress_label = QtWidgets.QLabel()

        self.__layout.addWidget(self.__status_label)
        self.__layout.addWidget(self.__progress_bar)
        # self.__layout.addWidget(self.__current_item_label)
        self.__layout.addWidget(self.__file_progress_label)

        self.setLayout(self.__layout)

    def __update_ui(self):
        # self.__current_item_label.setText(self.__current_item)
        self.__file_progress_label.setText(
            f"{self.__processed_items}/{self.__total_items}"
        )

        try:
            current_percent = self.__processed_items / self.__total_items * 100
        except ZeroDivisionError:
            current_percent = 100
        self.__progress_bar.setValue(current_percent)

    def start_tasks(self):
        self.__thread.start()

    def update_progress(self, progress: ProgressData):
        """
        :param progress: : (status, payload) - status is -1, 0, 1
                payload: {arg1: data1, arg2: data2, ...}
        :return:
        """

        if progress.status == 1:
            self.__progress_bar.setMaximum(100)
            # Processing
            self.__current_item = progress.payload.get("current_item", "N/A")
            self.__processed_items = progress.payload.get("processed_items", 0)
            self.__update_ui()
        elif progress.status == 0:
            # Completed with success
            self.__return_function(**progress.payload)
            self.close()
        else:
            # Error happened, handle
            raise Exception(str(progress.payload))
