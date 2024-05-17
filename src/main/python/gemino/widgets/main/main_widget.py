# Original Widgets File, to be incrementally refactored in separate widgets

from PySide6 import QtWidgets, QtCore, QtGui
import os
import os.path as path

from ...threads.common import SizeCalcThread
from ..common import ProgressWindow, LoadingDialog, error_box
from ..common.utils import is_portable

# Typing assignment for easier code navigation
ProgressTuple = tuple[int, dict[str, dict]]


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
