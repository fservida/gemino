# Generic utils for gemino's

from PySide2.QtCore import QThread, Signal
import os
import os.path as path


class SizeCalcThread(QThread):
    data_ready = Signal(object)

    def __init__(self, paths=None):
        super().__init__()
        if paths is None:
            paths = []
        self.paths = paths

    def run(self):
        dir_size = 0
        total_files = 0
        for path in self.paths:
            if os.path.isdir(path):
                for dirpath, dirnames, filenames in os.walk(path):
                    for filename in filenames:
                        try:
                            filepath = os.path.join(dirpath, filename)
                            dir_size += os.path.getsize(filepath)
                            total_files += 1
                        except (FileNotFoundError, OSError):
                            pass
            else:
                try:
                    dir_size += os.path.getsize(path)
                    total_files += 1
                except (FileNotFoundError, OSError):
                    pass

        self.data_ready.emit((dir_size, total_files))
        self.quit()