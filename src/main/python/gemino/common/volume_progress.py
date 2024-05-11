from PySide6 import QtWidgets, QtCore
from datetime import datetime, timedelta
import os
import webbrowser

from .log_dialog import LogDialog


class VolumeProgress(QtWidgets.QWidget):
    __STATUSES = {
        "copy": "Copying Files",
        "idle": "Idle",
        "hashing": "Verifying Hash",
        "done": "Done",
        "error_copy": "Copy Error",
        "error_hash": "Hash Verification Error",
        "error_io": "Lost Communication to Device",
    }

    def __init__(
        self,
        volume_name,
        total_bytes,
        total_files,
        aff4_filename: str = "",
        aff4_verify: bool = False,
    ):
        super().__init__()

        # Init Data
        self.__status = "idle"
        self.__verified = 0
        self.__current_file = "-"
        self.__processed_files = 0
        self.__total_files = total_files
        self.__processed_bytes = 0
        self.__previous_bytes_granular = (
            0  # Processed bytes updated with minimum 1 second granularity
        )
        self.__total_bytes = total_bytes
        self.__volume_name = volume_name
        self.__previous_time = datetime.now()
        self.__speed = 0
        self.__eta = timedelta(seconds=0)
        self.__aff4_filename = aff4_filename
        self.__aff4_verify = aff4_verify
        self.__log = ""
        self.__finished = False

        # UI
        self.__setup_ui()
        self.__update_ui()

    def __setup_ui(self):
        self.__volume_label = QtWidgets.QLabel()
        self.__current_status_label = QtWidgets.QLabel()
        self.__current_status_label.setAlignment(
            QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter
        )
        self.__progress_bar = QtWidgets.QProgressBar()
        self.__current_file_label = QtWidgets.QLabel()
        self.__size_progress_label = QtWidgets.QLabel()
        self.__size_progress_label.setAlignment(
            QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter
        )
        self.__speed_label = QtWidgets.QLabel()
        self.__speed_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.__eta_label = QtWidgets.QLabel()
        self.__eta_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.__file_progress_label = QtWidgets.QLabel()
        self.__file_progress_label.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
        )
        if self.__aff4_verify:
            self.__open_folder_button = QtWidgets.QPushButton("Open Container Folder")
        else:
            self.__open_folder_button = QtWidgets.QPushButton("Open Destination")
        self.__open_folder_button.clicked.connect(self.__open_folder)

        self.__show_log_button = QtWidgets.QPushButton("Show Log")
        self.__show_log_button.clicked.connect(self.__show_log)

        self.__layout_container = QtWidgets.QVBoxLayout()
        self.__layout_first_row = QtWidgets.QHBoxLayout()
        self.__layout_third_row = QtWidgets.QHBoxLayout()
        self.__layout_fourth_row = QtWidgets.QHBoxLayout()
        self.__layout_first_row.addWidget(self.__volume_label)
        self.__layout_first_row.addWidget(self.__current_status_label)
        self.__layout_first_row.addWidget(self.__open_folder_button)
        self.__layout_third_row.addWidget(self.__current_file_label)
        self.__layout_fourth_row.addWidget(self.__size_progress_label)
        self.__layout_fourth_row.addWidget(self.__speed_label)
        self.__layout_fourth_row.addWidget(self.__eta_label)
        self.__layout_fourth_row.addWidget(self.__file_progress_label)

        self.__layout_container.addLayout(self.__layout_first_row)
        self.__layout_container.addWidget(
            self.__progress_bar
        )  # "Second Row" Dedicated to Progress Bar
        self.__layout_container.addWidget(self.__show_log_button)
        self.__layout_container.addLayout(self.__layout_third_row)
        self.__layout_container.addLayout(self.__layout_fourth_row)

        self.setLayout(self.__layout_container)

    def __update_ui(self):
        if self.__aff4_filename:
            self.__volume_label.setText(
                os.path.join(self.__volume_name, self.__aff4_filename)
            )
        else:
            self.__volume_label.setText(self.__volume_name)
        self.__current_status_label.setText(VolumeProgress.__STATUSES[self.__status])
        self.__current_file_label.setText(self.current_file_truncated)
        self.__size_progress_label.setText(
            "{:.2f} / {:.2f} GB".format(
                self.__processed_bytes / 10**9, self.__total_bytes / 10**9
            )
        )
        self.__file_progress_label.setText(
            "{} / {} files".format(self.__processed_files, self.__total_files)
        )
        self.__speed_label.setText(self.speed)
        self.__eta_label.setText(
            str(self.__eta).split(".")[0]
        )  # split ETA string on microsecond separator if present

        if self.__aff4_verify:
            self.__show_log_button.setHidden(not self.__finished)
        else:
            self.__show_log_button.setHidden(True)

        try:
            current_percent = self.__processed_bytes / self.__total_bytes * 100
        except ZeroDivisionError:
            current_percent = 100
        self.__progress_bar.setValue(current_percent)

    @property
    def processed_bytes(self):
        return self.__processed_bytes

    @processed_bytes.setter
    def processed_bytes(self, processed_bytes):
        processed_bytes = int(processed_bytes)
        if not processed_bytes or processed_bytes < self.__processed_bytes:
            # print("Started Copy or Verification")
            self.__previous_bytes_granular = processed_bytes
        self.__processed_bytes = processed_bytes

        # Calculate time elapsed since last update, set previous time to current update time
        current_time = datetime.now()
        delta_time = current_time - self.__previous_time
        if delta_time.total_seconds() >= 1:
            self.__previous_time = current_time

            # Calculate bytes written since last update
            delta_bytes = self.__processed_bytes - self.__previous_bytes_granular
            self.__previous_bytes_granular = self.__processed_bytes

            # Use previously calculated deltas to establish speed and ETA
            elapsed_seconds = (
                delta_time.total_seconds() + delta_time.microseconds / 10**6
            )
            try:
                self.__speed = delta_bytes / elapsed_seconds  # In bytes
                remaining_bytes = self.__total_bytes - self.processed_bytes
                remaining_seconds = remaining_bytes / self.__speed
                self.__eta = timedelta(seconds=remaining_seconds)
                # print(self.__speed, delta_bytes, elapsed_seconds, self.__eta)
            except ZeroDivisionError:
                # elapsed_seconds == 0
                # print(
                #     f"Zero division error!\n"
                #     f"Seconds: {elapsed_seconds} "
                #     f"- Processed Bytes: {processed_bytes} "
                #     f"- Previous Bytes: {self.__previous_bytes_granular} "
                #     f"- Delta Bytes: {delta_bytes} "
                #     f"- Speed (Bytes/s): {self.__speed}"
                # )
                pass

        # Finally Update UI
        self.__update_ui()

    @property
    def speed(self):
        bytes_per_seconds = self.__speed
        if bytes_per_seconds >= 10**9:
            return f"{bytes_per_seconds / 10 ** 9:.2f} GB/s"
        elif bytes_per_seconds >= 10**6:
            return f"{bytes_per_seconds / 10 ** 6:.2f} MB/s"
        elif bytes_per_seconds >= 10**3:
            return f"{bytes_per_seconds / 10 ** 3:.2f} KB/s"
        else:
            return f"{float(bytes_per_seconds):.2f} Bytes/s"

    @property
    def processed_files(self):
        return self.__processed_files

    @processed_files.setter
    def processed_files(self, processed_files):
        self.__processed_files = int(processed_files)
        self.__update_ui()

    @property
    def status(self):
        return VolumeProgress.__STATUSES[self.__status]

    @status.setter
    def status(self, status):
        if str(status) not in VolumeProgress.__STATUSES:
            raise ValueError("Invalid Status Provided")
        self.__status = status
        self.__update_ui()

    @property
    def current_file(self):
        return self.__current_file

    @current_file.setter
    def current_file(self, current_file):
        self.__current_file = str(current_file)
        self.__update_ui()

    @property
    def current_file_truncated(self):
        MAX_LEN = 45
        if len(self.__current_file) <= MAX_LEN + 3:
            return self.__current_file
        else:
            return f"{self.current_file[:25]}...{self.__current_file[-25:]}"

    @property
    def volume(self):
        return self.__volume_name

    @volume.setter
    def volume(self, volume):
        raise PermissionError(
            "The Volume associated to a widget cannot be changed after the widget creation!"
        )

    def __open_folder(self):
        if self.__aff4_verify:
            webbrowser.open(f"file://{os.path.dirname(self.__volume_name)}")
        else:
            webbrowser.open(f"file://{self.__volume_name}")

    def write_log(self, log: str):
        self.__log += log

    def __show_log(self):
        self.log_dialog = LogDialog(
            self, f"Verification Log for {self.volume}", self.__log
        )
        self.log_dialog.setWindowFlags(QtCore.Qt.CustomizeWindowHint | QtCore.Qt.Dialog)
        self.log_dialog.setModal(True)
        self.log_dialog.setWindowModality(QtCore.Qt.ApplicationModal)
        self.log_dialog.open()

    def isFinished(self, finished: bool):
        self.__finished = finished
        self.__update_ui()
