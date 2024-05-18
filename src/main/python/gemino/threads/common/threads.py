from PySide6.QtCore import QThread, Signal

from .utils import ProgressData


class TaskThread(QThread):
    task_progress = Signal(object)

    def run(self):
        try:
            self.task()
        except Exception as error:
            raise
            self.task_progress.emit(ProgressData(-1, error))

    def task(self):
        raise NotImplementedError
