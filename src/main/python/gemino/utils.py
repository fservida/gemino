# Generic utils for gemino's

from PySide6.QtCore import QThread, Signal
import os
import os.path as path


class SizeCalcThread(QThread):
    data_ready = Signal(object)

    def __init__(self, folder="."):
        super().__init__()
        self.folder = folder

    def run(self):
        dir_size = 0
        total_files = 0
        for dirpath, dirnames, filenames in os.walk(self.folder):
            for filename in filenames:
                try:
                    filepath = path.join(dirpath, filename)
                    dir_size += path.getsize(filepath)
                    total_files += 1
                except (FileNotFoundError, OSError):
                    pass

        self.data_ready.emit((dir_size, total_files))
        self.quit()