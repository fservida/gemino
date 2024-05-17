from PySide6.QtCore import QThread, Signal
from copy import deepcopy

from ..common.utils import ProgressData
from ..copy.utils import CopyBuffer


class ExportThread(QThread):
    copy_progress = Signal(object)

    def __init__(
        self,
        src,
        destinations: list,
        total_files: int,
        total_bytes: int,
    ):
        """

        :param src: Source file object, should be bufferedIO like,
               already open in RB mode
        :param destinations: destination files, should be bufferedIO like,
               already open in WB mode (Should be list of 1 item)
        :param hashes: empty list
        :param total_files: Kept for compatibility with ProgressWindow
        :param total_bytes: Kept for compatibility with ProgressWindow
        :param metadata: Kept for compatibility with ProgressWindow
        :param aff4: Kept for compatibility with ProgressWindow
        :param aff4_filename: Kept for compatibility with ProgressWindow
        """
        super().__init__()
        # Only store parameters needed for file export
        self.src_file = src
        self.destinations = destinations
        self.total_files = total_files
        self.total_bytes = total_bytes

    def run(self):
        try:
            self.export_file()
        except Exception as error:
            raise
            self.copy_progress.emit(ProgressData(-1, error))

    def export_file(self):
        print("Exporting selected file...")

        buffer_size = 64 * 1024 * 1024  # Read 64M at a time

        filecount = 0
        copied_size = 0

        # Send initial window update
        self.copy_progress.emit(
            ProgressData(
                7,
                {
                    dst.name: {
                        "status": "exporting",
                        "processed_bytes": copied_size,
                        "processed_files": filecount,
                        "current_file": str(self.src_file.urn),
                    }
                    for dst in self.destinations
                },
            )
        )

        data = self.src_file.read(buffer_size)
        while data:

            threads = []

            # Create a full in-memory copy of the buffer read to avoid issues with concurrency
            # when reading the new stream as the same time the old is being written.
            # Not sure if really needed but performance impact is negligible and reduces risks.
            data_current = deepcopy(data)

            # Forbid thread termination while we have active child threads
            # If not done, the threads will return to a non-existing thread and crash the application
            # (I think)
            self.setTerminationEnabled(False)

            for dst in self.destinations:
                thread = CopyBuffer(data_current, dst)  # Threaded Version
                thread.start()  # Threaded Version
                threads.append(thread)  # Threaded Version

            copied_size += len(data_current)

            data = self.src_file.read(buffer_size)

            for thread in threads:
                thread.join()

            # All the spawned threads have exited, allow the termination of this thread again
            self.setTerminationEnabled(True)

            self.copy_progress.emit(
                ProgressData(
                    7,
                    {
                        dst.name: {
                            "processed_bytes": copied_size,
                            "processed_files": filecount,
                            "status": "exporting",
                            "current_file": str(self.src_file.urn),
                        }
                        for dst in self.destinations
                    },
                )
            )

        filecount = 1

        # End of copy reached
        self.copy_progress.emit(
            ProgressData(
                7,
                {
                    dst.name: {
                        "processed_bytes": copied_size,
                        "processed_files": filecount,
                        "status": "done",
                        "current_file": str(self.src_file.urn),
                    }
                    for dst in self.destinations
                },
            )
        )
        print("Done!")
        self.copy_progress.emit(ProgressData(8, {}))
