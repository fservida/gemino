import pprint
import traceback

from PySide6 import QtWidgets, QtCore, QtGui
from datetime import datetime, timedelta
import webbrowser
import os
import os.path as path
from pathlib import Path

from .utils import SizeCalcThread
from .copy.utils import ProgressData
from .copy.logical.copy import CopyThread, VerifyThread
from .copy.logical.aff4 import get_container_summary, get_metadata
from .view.advanced import AdvancedWidget

# Typing assignment for easier code navigation
ProgressTuple = tuple[int, dict[str, dict]]


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


class LoadingDialog(QtWidgets.QDialog):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Loading")
        self.label = QtWidgets.QLabel("Collecting File Information")
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)


def error_box(parent, text, subtitle="", details=""):
    message = QtWidgets.QMessageBox(parent)  # "Error", "No writable drive selected!"
    message.setIcon(QtWidgets.QMessageBox.Warning)
    message.setText(text)
    message.setInformativeText(subtitle)
    message.setDetailedText(details)
    message.setWindowTitle("Error")
    message.setStandardButtons(QtWidgets.QMessageBox.Ok)
    message.setWindowModality(QtCore.Qt.WindowModal)
    message.exec()


def is_portable():
    macos_path = Path(r"/Applications/gemino.app")
    windows_path = Path(r"C:\Program Files (x86)\gemino")
    application_path = Path(QtCore.QCoreApplication.applicationDirPath())
    if (
        macos_path in application_path.parents
        or windows_path in application_path.parents
    ):
        return False
    return True


class MainWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent=parent)

        # Do not use persistent settings if app is portable to reduce system modifications on copies from live systems
        if not is_portable():
            self.settings = QtCore.QSettings("ch.francescoservida", "Gemino")

        # App default configuration via file
        # Ini files with settings that will be imposed and will not be changeable by user.
        self.managed_settings = None
        self.managed_logo = (
            None  # interface/logo        -> If set logo will be displayed in interface
        )
        self.managed_algorithms = None  # hashing/algorithms    -> If set forces the usage of algorithms included in comma separated list
        self.managed_destinations_aff4 = (
            None  # destinations/aff4     -> If true forces the creation of AFF4 images
        )
        self.managed_destinations_drives = (
            None  # destinations/drives   -> If false disables the drives box
        )
        if os.path.exists("config.ini"):
            self.managed_settings = QtCore.QSettings(
                "config.ini", QtCore.QSettings.IniFormat
            )
            self.managed_logo = self.managed_settings.value("interface/logo", None)
            if self.managed_logo is not None and not os.path.exists(self.managed_logo):
                self.managed_logo = None
            self.managed_algorithms = self.managed_settings.value(
                "hashing/algorithms", None
            )
            if self.managed_algorithms is not None:
                try:
                    assert isinstance(self.managed_algorithms, list)
                    managed_algorithms = self.managed_algorithms
                except AssertionError:
                    if isinstance(self.managed_algorithms, str):
                        managed_algorithms = [self.managed_algorithms]
                    else:
                        managed_algorithms = None
                if (
                    managed_algorithms is not None
                ):  # if wrong value supplied keep none and do not force set empty list.
                    allowed_algorithms = ["md5", "sha1", "sha256"]
                    self.managed_algorithms = []
                    for algorithm in managed_algorithms:
                        if algorithm in allowed_algorithms:
                            self.managed_algorithms.append(algorithm)
            self.managed_destinations_aff4 = self.managed_settings.value(
                "destinations/aff4", None
            )
            if self.managed_destinations_aff4 is not None:
                self.managed_destinations_aff4 = (
                    self.managed_destinations_aff4.lower() == "true"
                )
            self.managed_destinations_drives = self.managed_settings.value(
                "destinations/drives", None
            )
            if self.managed_destinations_drives is not None:
                self.managed_destinations_drives = (
                    self.managed_destinations_drives.lower() == "true"
                )

        # Instantiate Widgets
        # Source Dir
        self.src_dir_dialog = QtWidgets.QFileDialog(self)
        self.src_dir_dialog.setWindowTitle("Select Source Folder")
        self.src_dir_dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        self.src_dir_dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly)
        self.src_dir_dialog.setWindowModality(QtCore.Qt.WindowModal)
        self.src_dir_dialog_button = QtWidgets.QPushButton("Choose Source Folder")
        self.src_dir_dialog_button.clicked.connect(self.open_files)
        self.src_dir_label = QtWidgets.QLabel("No Directory Selected")
        self.src_dir_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.files_count_label = QtWidgets.QLabel("0 Files")
        self.files_count_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.size_label = QtWidgets.QLabel("0 GB")
        self.size_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        # Destination Dir
        self.dst_vbar = QtWidgets.QFrame()
        self.dst_vbar.setFrameShape(QtWidgets.QFrame.VLine)
        self.destinations_label = QtWidgets.QLabel("Destinations:")
        self.dst_dir_dialog = QtWidgets.QFileDialog(self)
        self.dst_dir_dialog.setWindowTitle("Select Destination Folder")
        self.dst_dir_dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        self.dst_dir_dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly)
        self.dst_dir_dialog.setWindowModality(QtCore.Qt.WindowModal)
        self.dst_dir_dialog_button = QtWidgets.QPushButton("Choose Destination Folder")
        self.dst_dir_dialog_button.clicked.connect(self.select_dst_folder)
        self.dst_dir_label = QtWidgets.QLabel("No Directory Selected")
        self.dst_dir_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.dst_dir_information_label = QtWidgets.QLabel(
            "Select a destination folder to view storage details"
        )
        # Drive buttons
        self.select_all_button = QtWidgets.QPushButton("Select All Drives")
        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button = QtWidgets.QPushButton("Deselect All Drives")
        self.deselect_all_button.clicked.connect(self.deselect_all)
        self.refresh_button = QtWidgets.QPushButton("Refresh Available Drives")
        self.refresh_button.clicked.connect(self.refresh_button_handler)
        # Copy Buttons
        self.run_copy_button = QtWidgets.QPushButton("Start Copy")
        self.run_copy_button.clicked.connect(self.start_copy)
        # Volumes
        self.volumes_list_label = QtWidgets.QLabel("Target Drives:")
        self.volumes_list = QtWidgets.QListWidget(self)
        if self.managed_destinations_drives is not None:
            self.volumes_list_label.setDisabled(not self.managed_destinations_drives)
            self.volumes_list.setDisabled(not self.managed_destinations_drives)
            self.select_all_button.setDisabled(not self.managed_destinations_drives)
            self.deselect_all_button.setDisabled(not self.managed_destinations_drives)
            self.refresh_button.setDisabled(not self.managed_destinations_drives)
        # Report & Hashing
        self.report_hbar = QtWidgets.QFrame()
        self.report_hbar.setFrameShape(QtWidgets.QFrame.HLine)
        self.operator_name_label = QtWidgets.QLabel("Operator:")
        self.operator_name_text_field = QtWidgets.QLineEdit()
        self.intake_number_label = QtWidgets.QLabel("Intake:")
        self.intake_number_text_field = QtWidgets.QLineEdit()
        self.notes_label = QtWidgets.QLabel("Notes:")
        self.notes_text_field = QtWidgets.QTextEdit()
        self.init_hashing_widgets()
        # AFF4 Support
        self.aff4_checkbox = QtWidgets.QCheckBox("Write to AFF4 Container", self)
        self.aff4_checkbox.stateChanged.connect(self.toggle_aff4_filename)
        self.aff4_filename_label = QtWidgets.QLabel(
            "AFF4 Container Filename (w/o extension):"
        )
        self.aff4_filename = QtWidgets.QLineEdit()
        self.toggle_aff4_filename()
        if self.managed_destinations_aff4 is not None:
            self.aff4_checkbox.setChecked(self.managed_destinations_aff4)
            self.aff4_checkbox.setDisabled(True)
            self.aff4_filename_label.setDisabled(not self.managed_destinations_aff4)
            self.aff4_filename.setDisabled(not self.managed_destinations_aff4)

        # Layout Management
        self.window_layout = QtWidgets.QVBoxLayout()
        if self.managed_logo is not None:
            pixmap = QtGui.QPixmap(self.managed_logo)
            self.logo_label = QtWidgets.QLabel()
            self.logo_label.setPixmap(pixmap.scaledToHeight(150))
            self.window_layout.addWidget(
                self.logo_label, alignment=QtCore.Qt.AlignCenter
            )
        if self.managed_settings is not None:
            self.managed_settings_label = QtWidgets.QLabel(
                "Some of these settings may be managed by your organization."
            )
            self.managed_settings_label.setDisabled(True)
            self.window_layout.addWidget(
                self.managed_settings_label, alignment=QtCore.Qt.AlignCenter
            )
        self.layout = QtWidgets.QHBoxLayout()
        self.window_layout.addLayout(self.layout)
        self.left_layout = QtWidgets.QVBoxLayout()
        self.right_layout = QtWidgets.QVBoxLayout()
        self.layout.addLayout(self.left_layout)
        self.layout.addWidget(self.dst_vbar)
        self.layout.addLayout(self.right_layout)
        self.src_dir_dialog_layout = QtWidgets.QHBoxLayout()
        self.src_dir_dialog_layout.addWidget(self.src_dir_dialog_button)
        self.src_dir_dialog_layout.addWidget(self.src_dir_label)
        self.left_layout.addLayout(self.src_dir_dialog_layout)
        self.file_info_layout = QtWidgets.QHBoxLayout()
        self.file_info_layout.addWidget(self.files_count_label)
        self.file_info_layout.addWidget(self.size_label)
        self.left_layout.addLayout(self.file_info_layout)
        self.left_layout.addWidget(self.report_hbar)
        self.metadata_layout = QtWidgets.QHBoxLayout()
        self.metadata_layout.addWidget(self.operator_name_label)
        self.metadata_layout.addWidget(self.operator_name_text_field)
        self.metadata_layout.addWidget(self.intake_number_label)
        self.metadata_layout.addWidget(self.intake_number_text_field)
        self.left_layout.addLayout(self.metadata_layout)
        self.left_layout.addWidget(self.notes_label)
        self.left_layout.addWidget(self.notes_text_field)
        self.hash_layout = QtWidgets.QHBoxLayout()
        self.hash_layout.addWidget(self.hash_label)
        self.hash_layout.addWidget(self.md5_checkbox)
        self.hash_layout.addWidget(self.sha1_checkbox)
        self.hash_layout.addWidget(self.sha256_checkbox)
        self.left_layout.addLayout(self.hash_layout)
        # AFF4
        self.aff4_layout = QtWidgets.QVBoxLayout()
        self.aff4_checkbox_layout = QtWidgets.QHBoxLayout()
        self.aff4_checkbox_layout.addWidget(self.aff4_checkbox)
        self.aff4_filename_layout = QtWidgets.QHBoxLayout()
        self.aff4_filename_layout.addWidget(self.aff4_filename_label)
        self.aff4_filename_layout.addWidget(self.aff4_filename)
        self.aff4_layout.addLayout(self.aff4_checkbox_layout)
        self.aff4_layout.addLayout(self.aff4_filename_layout)
        self.left_layout.addLayout(self.aff4_layout)
        # Right Side
        self.right_layout.addWidget(self.destinations_label)
        self.dst_dir_dialog_layout = QtWidgets.QHBoxLayout()
        self.dst_dir_dialog_layout.addWidget(self.dst_dir_dialog_button)
        self.dst_dir_dialog_layout.addWidget(self.dst_dir_label)
        self.right_layout.addLayout(self.dst_dir_dialog_layout)
        self.right_layout.addWidget(self.dst_dir_information_label)
        self.right_layout.addWidget(self.volumes_list_label)
        self.right_layout.addWidget(self.volumes_list)
        self.volumes_select_layout = QtWidgets.QHBoxLayout()
        self.volumes_select_layout.addWidget(self.select_all_button)
        self.volumes_select_layout.addWidget(self.deselect_all_button)
        self.volumes_select_layout.addWidget(self.refresh_button)
        self.right_layout.addLayout(self.volumes_select_layout)
        self.right_layout.addWidget(self.run_copy_button)
        self.setLayout(self.window_layout)

        # Init data and fill widgets
        self.dir_size = 0
        self.dst_folder = None
        self.get_volumes()
        self.populate_volumes_widget()

    def get_volumes(self):
        # Only Store Volumes in ready state and exclude main system disk
        self.volumes = [
            volume
            for volume in QtCore.QStorageInfo.mountedVolumes()
            if (not volume.isRoot() and volume.isReady())
        ]

    def populate_volumes_widget(self):
        self.volumes_list.clear()
        self.volumes_list.setItemAlignment(QtCore.Qt.AlignCenter)

        for volume in self.volumes:
            if not volume.isReadOnly() and volume.bytesFree() > self.dir_size:
                item = QtWidgets.QListWidgetItem(
                    "{} - {} - {} - {} - {:.2f} GB Free".format(
                        volume.rootPath(),
                        volume.name(),
                        volume.device().data().decode(),
                        volume.fileSystemType().data().decode(),
                        volume.bytesFree() / 10**9,
                    )
                )
                item.setData(256, volume)
                self.volumes_list.addItem(item)
            else:
                errors = []
                if volume.isReadOnly():
                    errors.append("ReadOnly")
                if volume.bytesFree() < self.dir_size:
                    errors.append("Insufficient Space")
                item = QtWidgets.QListWidgetItem(
                    "{} - {} - {:.2f} GB Free - ! {} !".format(
                        volume.name(),
                        volume.fileSystemType().data().decode(),
                        volume.bytesFree() / 10**9,
                        ", ".join(errors),
                    )
                )
                item.setData(256, volume)
                item.setForeground(QtGui.QColor(255, 0, 0))
                self.volumes_list.addItem(item)
        self.volumes_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

    def refresh_button_handler(self):
        self.get_volumes()
        self.populate_volumes_widget()

    def start_copy(self):
        if not hasattr(self, "source_dir") or not self.source_dir:
            error_box(self, "No Directory Selected")
            return

        # Save hashing algorithms settings
        if not is_portable():
            hash_algos = self.hashing_algos.buttons()
            for hash_algo in hash_algos:
                self.settings.setValue(hash_algo.text(), hash_algo.isChecked())
            self.settings.sync()

        # Launch Copy
        hash_algos = [
            hash_algo.text()
            for hash_algo in self.hashing_algos.buttons()
            if hash_algo.isChecked()
        ]
        dst_volumes = [
            item.data(256).rootPath()
            for item in self.volumes_list.selectedItems()
            if not item.data(256).isReadOnly()
            and item.data(256).bytesFree() > self.dir_size
        ]
        if self.dst_folder:
            dst_folder_storage_info = QtCore.QStorageInfo(self.dst_folder)
            dst_folder_writable = os.access(self.dst_folder, os.W_OK)
            if (
                dst_folder_storage_info.isReady()
                and dst_folder_writable
                and dst_folder_storage_info.bytesFree() > self.dir_size
            ):
                dst_volumes.append(self.dst_folder)

        if self.aff4_checkbox.isChecked() and len(dst_volumes) > 1:
            # error_box("Writing to Multiple Destinations When Using AFF4 Creates Container Files With Different Hashes.\n\n"
            #          "You will have to verify the content of the AFF4 containers when comparing containers and not the container itself.\n")
            error_box(self, "Only One Destination Supported When Using AFF4 Containers")
            return

        if self.aff4_checkbox.isChecked():
            error_box(
                self,
                "Containers in AFF4 format are compliant with standard but might not be recognized by all forensic tools.\n"
                "If your tool does not support AFF4-L or is unable to process, import the container as a zip file.",
            )

        dst_volumes = self.check_existing(dst_volumes)
        dst_volumes = self.normalize_paths(dst_volumes)

        if dst_volumes:
            # At least one drive selected and writable
            self.progress = ProgressWindow(
                self,
                self.source_dir,
                dst_volumes,
                hash_algos,
                self.files_count,
                self.dir_size,
                self.metadata,
                self.aff4_checkbox.isChecked(),
                self.aff_filename,
            )
            self.progress.setWindowFlags(
                QtCore.Qt.CustomizeWindowHint | QtCore.Qt.Dialog
            )
            self.progress.setWindowModality(QtCore.Qt.ApplicationModal)
            self.progress.open()
            self.progress.start_tasks()
        else:
            error_box(
                self,
                "No writable/valid drive selected or all destinations have been skipped!",
            )

    # TODO - If AFF4 -> Check if same filename exists and not if folder is empty.
    def check_existing(self, volumes):
        if not self.aff4_checkbox.isChecked():
            base_path = self.src_base_path
            for i in range(len(volumes)):
                dst_path = os.path.join(volumes[i], base_path)
                if os.path.exists(dst_path) and os.listdir(dst_path):
                    # Folder not empty alert user
                    print(f"{dst_path} not empty!")
                    if self.confirm_overwrite(dst_path):
                        print("User chose to overwrite")
                        pass
                    else:
                        # If user cancels:
                        print("User chose to skip folder, remove from destinations.")
                        volumes.pop(i)
            return volumes
        else:
            for i in range(len(volumes)):
                dst_path = os.path.join(volumes[i], self.aff_filename)
                if os.path.exists(dst_path):
                    # Folder not empty alert user
                    print(f"{dst_path} already exists!")
                    if self.confirm_overwrite(dst_path):
                        print("User chose to overwrite")
                        pass
                    else:
                        # If user cancels:
                        print("User chose to skip container, remove from destinations.")
                        volumes.pop(i)
            return volumes

    @property
    def src_base_path(self):
        base_path = (
            path.basename(path.normpath(self.source_dir))
            if path.basename(path.normpath(self.source_dir)) != ""
            else "[root]"
        )
        return base_path

    def normalize_paths(self, destinations: list):
        for i in range(len(destinations)):
            destination = destinations[i]
            destination = os.path.normpath(destination)
            destinations[i] = destination

        return destinations

    @property
    def aff_filename(self):
        """
        Append AFF4 Container to specified destinations if AFF4 is enabled
        :param destinations: list of destination PATHS
        :return: destinations: list of AFF4 container PATHS
        """
        aff4_filename = self.aff4_filename.text()
        if not aff4_filename:
            aff4_filename = self.src_base_path
        aff4_filename += ".aff4"

        return aff4_filename

    def init_hashing_widgets(self):
        # Hash Related Widgets
        hash_algos = {
            "md5": None,
            "sha1": None,
            "sha256": None,
        }
        if self.managed_algorithms is not None:
            for hash_algo in hash_algos:
                hash_algos[hash_algo] = hash_algo in self.managed_algorithms
        elif not is_portable():
            for hash_algo in hash_algos:
                stored_setting = self.settings.value(hash_algo)
                if isinstance(stored_setting, str):
                    # Windows returns a string
                    hash_algos[hash_algo] = (
                        (stored_setting == "true")
                        if stored_setting is not None
                        else True
                    )
                else:
                    # macOS, returns a Boolean
                    hash_algos[hash_algo] = (
                        bool(stored_setting) if stored_setting is not None else True
                    )
        else:
            # By default use only MD5
            hash_algos = {"md5": True, "sha1": False, "sha256": False}

        self.hash_label = QtWidgets.QLabel("Hashing Algorithms: ")
        self.md5_checkbox = QtWidgets.QCheckBox("md5", self)
        self.md5_checkbox.setChecked(hash_algos["md5"])
        self.sha1_checkbox = QtWidgets.QCheckBox("sha1", self)
        self.sha1_checkbox.setChecked(hash_algos["sha1"])
        self.sha256_checkbox = QtWidgets.QCheckBox("sha256", self)
        self.sha256_checkbox.setChecked(hash_algos["sha256"])
        self.hashing_algos = QtWidgets.QButtonGroup(self)
        self.hashing_algos.setExclusive(False)
        self.hashing_algos.addButton(self.md5_checkbox)
        self.hashing_algos.addButton(self.sha1_checkbox)
        self.hashing_algos.addButton(self.sha256_checkbox)
        if self.managed_algorithms is not None:
            self.hash_label.setDisabled(True)
            self.md5_checkbox.setDisabled(True)
            self.sha1_checkbox.setDisabled(True)
            self.sha256_checkbox.setDisabled(True)

    def toggle_aff4_filename(self):
        self.aff4_filename_label.setDisabled(not self.aff4_checkbox.isChecked())
        self.aff4_filename.setDisabled(not self.aff4_checkbox.isChecked())

    def open_files(self):
        directory = ""
        try:
            directory = QtCore.QStandardPaths.standardLocations(
                QtCore.QStandardPaths.HomeLocation
            )[0]
        except:
            pass
        self.src_dir_dialog.setDirectory(directory)
        accepted = self.src_dir_dialog.exec()
        self.source_dir: str = None
        if accepted:
            self.source_dir = self.src_dir_dialog.selectedFiles()[0]
        self.src_dir_label.setText(
            self.source_dir if self.source_dir else "No Directory Selected"
        )
        if self.source_dir:
            self.get_size()

    def select_dst_folder(self):
        directory = ""
        try:
            directory = QtCore.QStandardPaths.standardLocations(
                QtCore.QStandardPaths.HomeLocation
            )[0]
        except:
            pass
        self.dst_dir_dialog.setDirectory(directory)
        accepted = self.dst_dir_dialog.exec()
        self.dst_folder: str = None
        if accepted:
            self.dst_folder = self.dst_dir_dialog.selectedFiles()[0]
        self.dst_dir_label.setText(
            self.dst_folder if self.dst_folder else "No Directory Selected"
        )
        if not self.dst_folder:
            self.dst_dir_information_label.setText(
                "Select a destination folder to view storage details"
            )
        self.dst_folder_check()

    def select_all(self):
        self.volumes_list.selectAll()

    def deselect_all(self):
        self.volumes_list.clearSelection()

    def get_size(self):
        # Create Loading Modal
        self.loading = LoadingDialog()
        self.loading.setModal(True)
        self.loading.setWindowFlags(QtCore.Qt.CustomizeWindowHint | QtCore.Qt.Dialog)
        self.loading.show()

        # Start Calculating size & File count
        self.thread = SizeCalcThread(self.source_dir)
        self.thread.data_ready.connect(
            self.size_calc_handle, QtCore.Qt.QueuedConnection
        )
        self.thread.start()

    def size_calc_handle(self, data):
        # Unpack Result
        self.dir_size, self.files_count = data

        self.size_label.setText("{:.2f} GB".format(self.dir_size / 10**9))
        self.files_count_label.setText("{} Files".format(self.files_count))
        self.populate_volumes_widget()

        # Kill Modal View
        self.loading.close()

    def dst_folder_check(self):
        if self.dst_folder:
            # Only execute if a destination folder has been selected
            dst_storage_info = QtCore.QStorageInfo(self.dst_folder)
            dst_bytes_available = dst_storage_info.bytesAvailable()
            dst_folder_writable = os.access(self.dst_folder, os.W_OK)
            if dst_bytes_available > self.dir_size:
                # Enough space available on destination
                self.dst_dir_information_label.setText(
                    "Enough space available on destination"
                )
            else:
                self.dst_dir_information_label.setText(
                    "NOT Enough space available on destination"
                )

            if dst_folder_writable and dst_storage_info.bytesFree() > self.dir_size:
                self.dst_dir_information_label.setText(
                    "On volume: {} - {} - {:.2f} GB Free".format(
                        dst_storage_info.name(),
                        dst_storage_info.fileSystemType().data().decode(),
                        dst_storage_info.bytesFree() / 10**9,
                    )
                )
            else:
                errors = []
                if not dst_folder_writable:
                    errors.append("ReadOnly")
                if dst_storage_info.bytesFree() < self.dir_size:
                    errors.append("Insufficient Space")
                self.dst_dir_information_label.setText(
                    "On volume: {} - {} - {:.2f} GB Free - ! {} !".format(
                        dst_storage_info.name(),
                        dst_storage_info.fileSystemType().data().decode(),
                        dst_storage_info.bytesFree() / 10**9,
                        ", ".join(errors),
                    )
                )
                # self.dst_dir_information_label.setTextColor(QtGui.QColor(255, 0, 0))

    @property
    def metadata(self):
        return {
            "operator": self.operator_name_text_field.text(),
            "intake": self.intake_number_text_field.text(),
            "notes": self.notes_text_field.toPlainText(),
        }

    def confirm_overwrite(self, path):
        if self.aff4_checkbox.isChecked():
            message = f"Container: {path} already exists and will be overwritten.\n\nDo you want to continue?"
        else:
            message = f"Directory: {path} is not empty.\nData contained may be overwritten without additional confirmation.\n\nDo you want to continue?"
        confirmation = QtWidgets.QMessageBox(self)
        confirmation.setIcon(QtWidgets.QMessageBox.Warning)
        confirmation.setText(message)
        confirmation.addButton(QtWidgets.QMessageBox.Yes)
        confirmation.addButton(QtWidgets.QMessageBox.No)
        confirmation.setWindowTitle("Confirm Overwrite")
        confirmation.setModal(True)
        confirmation.setWindowModality(QtCore.Qt.WindowModal)
        choice = confirmation.exec()
        if choice == QtWidgets.QMessageBox.Yes:
            return True
        else:
            return False


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, version):
        super().__init__()

        self.main_widget = QtWidgets.QWidget(self)
        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.setSpacing(10)
        self.main_widget.setLayout(self.main_layout)

        self.tab_widgets = QtWidgets.QTabWidget(self)
        self.home_widget = MainWidget()
        self.advanced_widget = AdvancedWidget()
        self.advanced_widget.open_button.clicked.connect(self.read_aff4_window_open)

        self.tab_widgets.addTab(self.home_widget, "Home")
        self.tab_widgets.addTab(self.advanced_widget, "Advanced")

        self.main_layout.addWidget(self.tab_widgets)
        self.setCentralWidget(self.main_widget)
        self.initMenu()
        self.version = version
        self.progress: ProgressWindow = None

    def initMenu(self):
        bar = self.menuBar()

        self.help = bar.addMenu("Help")
        self.about = QtGui.QAction("About")
        self.about.triggered.connect(self.about_box)
        self.help.addAction(self.about)

        self.tools = bar.addMenu("Tools")
        self.verify_menu = QtGui.QAction("Verify AFF4-L Container")
        self.verify_menu.triggered.connect(self.verify_aff4)
        self.tools.addAction(self.verify_menu)
        self.bar = bar

        self.read_menu = QtGui.QAction("Open AFF4-L Container")
        self.read_menu.triggered.connect(self.read_aff4_window_open)
        self.tools.addAction(self.read_menu)

    def about_box(self):
        message = QtWidgets.QMessageBox(self)
        message.setWindowModality(QtCore.Qt.WindowModal)
        message.setIcon(QtWidgets.QMessageBox.Information)
        message.setText("gemino")
        message.setInformativeText(
            f"gemino\n\nForensic logical imager and file duplicator\n\nv{self.version}\n\nDeveloped with ❤️ by Francesco Servida beside work at:\n - University of Lausanne\n - United Nations Investigative Team for Accountability of crimes committed by Da’esh/ISIL (UNITAD)\n\nLicensed under GPLv3\nhttps://opensource.org/licenses/GPL-3.0\nThird party dependencies: https://francescoservida.ch/gemino/LICENSES"
        )
        message.setWindowTitle("About")
        message.setStandardButtons(QtWidgets.QMessageBox.Ok)
        message.exec()

    def read_aff4_window_open(self):
        self.bar.setDisabled(True)
        self.src_container = QtWidgets.QFileDialog(self)
        self.src_container.setWindowTitle("Select AFF4-L Container to Open")
        self.src_container.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        self.src_container.setNameFilter("AFF4-L Containers (*.aff4)")
        self.src_container.setWindowModality(QtCore.Qt.WindowModal)
        directory = ""
        try:
            directory = QtCore.QStandardPaths.standardLocations(
                QtCore.QStandardPaths.HomeLocation
            )[0]
        except:
            pass
        self.src_container.setDirectory(directory)
        accepted = self.src_container.exec()
        self.bar.setDisabled(False)
        src_container_path: str = None
        if accepted:
            src_container_path = self.src_container.selectedFiles()[0]
        if src_container_path:
            try:
                volume, items = get_metadata(src_container_path)
                self.advanced_widget.populate(volume, items, src_container_path)
                self.resize(1400, 800)
            except Exception as e:
                error_box(
                    self,
                    "Unable to Open",
                    "An error occurred while opening the container. "
                    "It is possible the container is not in AFF4-L format or corrupted.",
                    traceback.format_exc(),
                )
                pass
        else:
            pass

        # self.resize(1200, 800)

    def verify_aff4(self):
        self.bar.setDisabled(True)
        self.src_container = QtWidgets.QFileDialog(self)
        self.src_container.setWindowTitle("Select AFF4-L Container to Verify")
        self.src_container.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        self.src_container.setNameFilter("AFF4-L Containers (*.aff4)")
        self.src_container.setWindowModality(QtCore.Qt.WindowModal)
        directory = ""
        try:
            directory = QtCore.QStandardPaths.standardLocations(
                QtCore.QStandardPaths.HomeLocation
            )[0]
        except:
            pass
        self.src_container.setDirectory(directory)
        accepted = self.src_container.exec()
        self.bar.setDisabled(False)
        src_container_path: str = None
        if accepted:
            src_container_path = self.src_container.selectedFiles()[0]
        if src_container_path:
            try:
                total_files, total_size = get_container_summary(src_container_path)
                self.progress = ProgressWindow(
                    self,
                    src_container_path,
                    total_files=total_files,
                    total_bytes=total_size,
                    aff4_verify=True,
                )
                self.progress.setWindowFlags(
                    QtCore.Qt.CustomizeWindowHint | QtCore.Qt.Dialog
                )
                self.progress.setModal(True)
                self.progress.setWindowModality(QtCore.Qt.ApplicationModal)
                self.progress.open()
                self.progress.start_tasks()
            except Exception as e:
                error_box(
                    self,
                    "Unable to Verify",
                    "An error occurred while opening the container. "
                    "It is possible the container is not in AFF4-L format or corrupted.",
                    traceback.format_exc(),
                )
                pass
        else:
            pass


class ErrorWindow(QtWidgets.QMainWindow):
    def __init__(self, error):
        super().__init__()
