from PySide6 import QtWidgets, QtCore
import os.path as path
from datetime import datetime
import traceback


from .volume_progress import VolumeProgress
from .error_box import error_box
from ...threads.copy.logical.copy import CopyThread, VerifyThread
from ...threads.copy.utils import ProgressData


class ProgressWindow(QtWidgets.QDialog):
    STATUSES = (
        "copying",
        "hashing",
        "end",
        "cancel",
        "verifying",
        "end_verify",
        "cancel_verify",
    )
    DESCRIPTIONS = {
        "copying": "Writing to Device, hashing source on the fly",
        "hashing": "Verifying data written to device",
        "end": "Copy and verification finished",
        "cancel": "File copy has been interrupted",
        "verifying": "Verifying integrity of container",
        "end_verify": "Container verification finished",
        "cancel_verify": "Container verification aborted",
    }

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        src: str,
        dst: list = [],
        hash_algos: list = [],
        total_files: int = 0,
        total_bytes: int = 0,
        metadata: list = [],
        aff4: bool = False,
        aff4_filename: str = "",
        aff4_verify: bool = False,
    ):
        super().__init__(parent=parent)

        # Labels
        if aff4_verify:
            window_title = "Verification Progress"
            cancel_label = "Cancel Verification"
        else:
            window_title = "Copy Progress"
            cancel_label = "Cancel Copy"

        self.setWindowTitle(window_title)
        self.status_label = QtWidgets.QLabel("")

        self.cancel_button = QtWidgets.QPushButton(cancel_label)
        self.cancel_button.clicked.connect(self.cancel)

        self.close_button = QtWidgets.QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.close_button.setHidden(True)

        self.volume_progresses: list[VolumeProgress] = []

        for destination in dst:
            if aff4:
                self.volume_progresses.append(
                    VolumeProgress(destination, total_bytes, total_files, aff4_filename)
                )
            else:
                self.volume_progresses.append(
                    VolumeProgress(destination, total_bytes, total_files)
                )
        if aff4_verify:
            self.volume_progresses.append(
                VolumeProgress(src, total_bytes, total_files, aff4_verify=True)
            )

        self.layout = QtWidgets.QVBoxLayout()
        self.layout2 = QtWidgets.QHBoxLayout()
        self.layout.addWidget(self.status_label)

        self.layout.addLayout(self.layout2)

        # Add Volumes Progresses Widgets
        for volume_progress in self.volume_progresses:
            self.layout.addWidget(volume_progress)

        self.layout.addWidget(self.close_button)
        self.layout.addWidget(self.cancel_button)
        self.setLayout(self.layout)

        # Init Data
        self.src = src
        self.dst = dst
        self.hash_algos = hash_algos
        self.total_files = total_files
        self.aff4 = aff4
        self.aff4_filename = aff4_filename

        if self.aff4:
            self.base_path = self.aff4_filename
        else:
            self.base_path = (
                path.basename(path.normpath(src))
                if path.basename(path.normpath(src)) != ""
                else "[root]"
            )

        self.processed_files = 0
        self.status = ProgressWindow.STATUSES[0]
        self.update_ui()

        # Start copying files
        if not aff4_verify:
            self.thread = CopyThread(
                src,
                dst,
                hash_algos,
                total_files,
                total_bytes,
                metadata,
                aff4,
                aff4_filename,
            )
            self.thread.copy_progress.connect(
                self.update_progress, QtCore.Qt.QueuedConnection
            )
        else:
            self.thread = VerifyThread(src, total_files, total_bytes)
            self.thread.verify_progress.connect(
                self.update_progress, QtCore.Qt.QueuedConnection
            )

    def start_tasks(self):
        self.thread.start()

    def update_progress(self, progress: ProgressData):
        """
        :param progress: : (status, data) - status is 0, 1 or 2 (for STATUSES)
                data: {dst: progress_status, dst2: progress_status, ...}
                progress_status: {'status': str, 'processed_bytes': int, 'processed_files: int, 'current_file': str}
        :return:
        """

        status = progress.status
        if status == -1:
            self.status = "cancel"
            self.update_ui()
            error_box(
                self,
                "Halp! An Error Occurred!",
                f"Bob is Sad T.T\n\nDetails:\n{progress.payload}",
            )
            return

        data = progress.payload
        self.status = ProgressWindow.STATUSES[status]
        if status not in (2, 5):
            for volume_progress in self.volume_progresses:
                # update Widget only if information about the volume are present in progress
                # (eg. parallel or current drive for serial)
                if volume_progress.volume in data:
                    progress_status = data[volume_progress.volume]
                    volume_progress.processed_bytes = progress_status["processed_bytes"]
                    volume_progress.processed_files = progress_status["processed_files"]
                    volume_progress.current_file = progress_status["current_file"]
                    volume_progress.status = progress_status["status"]
                    log = progress_status.get(
                        "log", None
                    )  # Support for ephemeral AFF4 verification log
                    if log:
                        volume_progress.write_log(log)
                else:
                    # If volume is not in data dictionary it means and error happened during the copy
                    # and it was removed from the destinations list
                    volume_progress.status = "error_copy"
        else:
            for volume_progress in self.volume_progresses:
                volume_progress.isFinished(True)

        self.update_ui()

    def update_ui(self):
        self.status_label.setText(self.DESCRIPTIONS[self.status])
        if self.status in ("end", "cancel", "end_verify", "cancel_verify"):
            self.close_button.setHidden(False)
            self.cancel_button.setHidden(True)

    def cancel(self):
        # Terminate the thread
        self.thread.terminate()
        self.status = self.STATUSES[3]  # cancel

        base_path = self.base_path
        for dst in self.dst:
            try:
                report_file_path = path.join(dst, f"{base_path}_copy_report.txt")
                with open(report_file_path, "a", encoding="utf-8") as report_file:
                    report_file.write(
                        f"\nUser interrupted copy process at: {datetime.now().isoformat()}"
                    )
            except FileNotFoundError as error:
                print(f"Error writing to report: {error}")
                error_box(self, "Error Writing to Report", traceback.format_exc())
        self.update_ui()