from PySide2 import QtWidgets, QtCore, QtGui

from .threads import SizeCalcThread, CopyThread


class VolumeProgress(QtWidgets.QWidget):
    __STATUSES = {
        'copy': 'Copying Files',
        'idle': 'Idle',
        'hashing': 'Verifying Hash',
        'done': 'Done',
        'error_copy': 'Copy Error',
        'error_hash': 'Hash Verification Error',
        'error_io': 'Lost Communication to Device'
    }

    def __init__(self, volume_name, total_bytes, total_files):
        super().__init__()

        # Init Data
        self.__status = 'idle'
        self.__verified = 0
        self.__current_file = 'test_file'
        self.__processed_files = 0
        self.__total_files = total_files
        self.__processed_bytes = 0
        self.__total_bytes = total_bytes
        self.__volume_name = volume_name

        # UI
        self.__setup_ui()
        self.__update_ui()

    def __setup_ui(self):
        self.__volume_label = QtWidgets.QLabel()
        self.__current_status_label = QtWidgets.QLabel()
        self.__current_status_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.__progress_bar = QtWidgets.QProgressBar()
        self.__current_file_label = QtWidgets.QLabel()
        self.__size_progress_label = QtWidgets.QLabel()
        self.__size_progress_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.__file_progress_label = QtWidgets.QLabel()
        self.__file_progress_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.__layout_container = QtWidgets.QVBoxLayout()
        self.__layout_first_row = QtWidgets.QHBoxLayout()
        self.__layout_third_row = QtWidgets.QHBoxLayout()
        self.__layout_first_row.addWidget(self.__volume_label)
        self.__layout_first_row.addWidget(self.__current_status_label)
        self.__layout_third_row.addWidget(self.__current_file_label)
        self.__layout_third_row.addWidget(self.__size_progress_label)
        self.__layout_third_row.addWidget(self.__file_progress_label)

        self.__layout_container.addLayout(self.__layout_first_row)
        self.__layout_container.addWidget(self.__progress_bar)  # "Second Row" Dedicated to Progress Bar
        self.__layout_container.addLayout(self.__layout_third_row)

        self.setLayout(self.__layout_container)

    def __update_ui(self):
        self.__volume_label.setText(self.__volume_name)
        self.__current_status_label.setText(VolumeProgress.__STATUSES[self.__status])
        self.__current_file_label.setText(self.__current_file)
        self.__size_progress_label.setText(
            "{:.2f} / {:.2f} GB".format(self.__processed_bytes / 10 ** 9, self.__total_bytes / 10 ** 9))
        self.__file_progress_label.setText("{} / {} files".format(self.__processed_files, self.__total_files))
        current_percent = self.__processed_bytes / self.__total_bytes * 100
        self.__progress_bar.setValue(current_percent)

    @property
    def processed_bytes(self):
        return self.__processed_bytes

    @processed_bytes.setter
    def processed_bytes(self, processed_bytes):
        self.__processed_bytes = int(processed_bytes)
        self.__update_ui()

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
    def volume(self):
        return self.__volume_name

    @volume.setter
    def volume(self, volume):
        raise PermissionError('The Volume associated to a widget cannot be changed after the widget creation!')


class ProgressWindow(QtWidgets.QDialog):
    STATUSES = ('copying', 'hashing', 'end', 'cancel')
    DESCRIPTIONS = {
        'copying': 'Writing to Device, hashing source on the fly',
        'hashing': 'Verifying data written to device',
        'end': 'Copy and verification finished',
        'cancel': 'File copy has been interrupted',
    }

    def __init__(self, src: str, dst: list, hash_algos: list, total_files: int, total_bytes: int):
        super().__init__()

        self.setWindowTitle("Copy Progress")
        self.status_label = QtWidgets.QLabel("")

        self.cancel_button = QtWidgets.QPushButton("Cancel Copy")
        self.cancel_button.clicked.connect(self.cancel)

        self.close_button = QtWidgets.QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.close_button.setHidden(True)

        self.volume_progresses = []
        for destination in dst:
            self.volume_progresses.append(VolumeProgress(destination, total_bytes, total_files))

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

        self.processed_files = 0
        self.status = ProgressWindow.STATUSES[0]
        self.update_ui()

        # Start copying files
        self.thread = CopyThread(src, dst, hash_algos, total_files)
        self.thread.copy_progress.connect(self.update_progress, QtCore.Qt.QueuedConnection)
        self.thread.start()

    def update_progress(self, progress: tuple):
        """
        :param progress: : (status, data) - status is 0, 1 or 2 (for STATUSES)
                data: {dst: progress_status, dst2: progress_status, ...}
                progress_status: {'status': str, 'processed_bytes': int, 'processed_files: int, 'current_file': str}
        :return:
        """
        status = progress[0]
        if status == -1:
            self.status = 'cancel'
            self.update_ui()
            error_box("Halp! An Error Occurred!", "Bob is Sad T.T")
            return

        data = progress[1]
        self.status = ProgressWindow.STATUSES[status]
        if status != 2:
            for volume_progress in self.volume_progresses:
                # update Widget only if information about the volume are present in progress
                # (eg. parallel or current drive for serial)
                if volume_progress.volume in data:
                    progress_status = data[volume_progress.volume]
                    volume_progress.processed_bytes = progress_status['processed_bytes']
                    volume_progress.processed_files = progress_status['processed_files']
                    volume_progress.current_file = progress_status['current_file']
                    volume_progress.status = progress_status['status']
                else:
                    # If volume is not in data dictionary it means and error happened during the copy
                    # and it was removed from the destinations list
                    volume_progress.status = 'error_copy'

        self.update_ui()

    def update_ui(self):
        self.status_label.setText(self.DESCRIPTIONS[self.status])
        if self.status == 'end' or self.status == 'cancel':
            self.close_button.setHidden(False)
            self.cancel_button.setHidden(True)

    def cancel(self):
        # Terminate the thread
        self.thread.terminate()
        self.status = self.STATUSES[3]  # cancel
        self.update_ui()


class LoadingDialog(QtWidgets.QDialog):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Loading")
        self.label = QtWidgets.QLabel("Collecting File Information")
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)


def error_box(text, subtitle="", details=""):
    message = QtWidgets.QMessageBox()  # "Error", "No writable drive selected!"
    message.setIcon(QtWidgets.QMessageBox.Warning)
    message.setText(text)
    message.setInformativeText(subtitle)
    message.setDetailedText(details)
    message.setWindowTitle("Error")
    message.setStandardButtons(QtWidgets.QMessageBox.Ok)
    message.exec_()


class MainWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.settings = QtCore.QSettings("ch.unil.esc-cyber", "Gemino")

        # Instantiate Widgets
        self.dir_dialog = QtWidgets.QFileDialog(self)
        self.dir_dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        self.dir_dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly)
        self.dir_dialog_button = QtWidgets.QPushButton("Choose Files")
        self.dir_dialog_button.clicked.connect(self.open_files)
        self.dir_label = QtWidgets.QLabel("No Directory Selected")
        self.files_count_label = QtWidgets.QLabel("0 Files")
        self.size_label = QtWidgets.QLabel("0 GB")
        self.select_all_button = QtWidgets.QPushButton("Select All Drives")
        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button = QtWidgets.QPushButton("Deselect All Drives")
        self.deselect_all_button.clicked.connect(self.deselect_all)
        self.refresh_button = QtWidgets.QPushButton("Refresh Available Drives")
        self.refresh_button.clicked.connect(self.refresh_button_handler)
        self.run_copy_button = QtWidgets.QPushButton("Start Copy")
        self.run_copy_button.clicked.connect(self.start_copy)
        self.volumes_list_label = QtWidgets.QLabel("Target Drives:")
        self.volumes_list = QtWidgets.QListWidget(self)
        self.init_hashing_widgets()

        # Layout Management
        self.layout = QtWidgets.QVBoxLayout()
        self.dir_dialog_layout = QtWidgets.QHBoxLayout()
        self.dir_dialog_layout.addWidget(self.dir_dialog_button)
        self.dir_dialog_layout.addWidget(self.dir_label)
        self.layout.addLayout(self.dir_dialog_layout)
        self.file_info_layout = QtWidgets.QHBoxLayout()
        self.file_info_layout.addWidget(self.files_count_label)
        self.file_info_layout.addWidget(self.size_label)
        self.layout.addLayout(self.file_info_layout)
        self.hash_layout = QtWidgets.QHBoxLayout()
        self.hash_layout.addWidget(self.hash_label)
        self.hash_layout.addWidget(self.md5_checkbox)
        self.hash_layout.addWidget(self.sha1_checkbox)
        self.hash_layout.addWidget(self.sha256_checkbox)
        self.layout.addLayout(self.hash_layout)
        self.layout.addWidget(self.volumes_list_label)
        self.layout.addWidget(self.volumes_list)
        self.volumes_select_layout = QtWidgets.QHBoxLayout()
        self.volumes_select_layout.addWidget(self.select_all_button)
        self.volumes_select_layout.addWidget(self.deselect_all_button)
        self.volumes_select_layout.addWidget(self.refresh_button)
        self.layout.addLayout(self.volumes_select_layout)
        self.layout.addWidget(self.run_copy_button)
        self.setLayout(self.layout)

        # Init data and fill widgets
        self.dir_size = 0
        self.get_volumes()
        self.populate_volumes_widget()

    def get_volumes(self):
        # Only Store Volumes in ready state and exclude main system disk
        self.volumes = [volume for volume in QtCore.QStorageInfo.mountedVolumes() if
                        (not volume.isRoot() and volume.isReady())]

    def populate_volumes_widget(self):
        self.volumes_list.clear()
        self.volumes_list.setItemAlignment(QtCore.Qt.AlignCenter)

        for volume in self.volumes:
            if not volume.isReadOnly() and volume.bytesFree() > self.dir_size:
                item = QtWidgets.QListWidgetItem(
                    "{} - {} - {:.2f} GB Free".format(volume.name(), volume.fileSystemType().data().decode(),
                                                      volume.bytesFree() / 10 ** 9))
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
                        volume.bytesFree() / 10 ** 9,
                        ", ".join(errors))
                )
                item.setData(256, volume)
                item.setTextColor(QtGui.QColor(255, 0, 0))
                self.volumes_list.addItem(item)
        self.volumes_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

    def refresh_button_handler(self):
        self.get_volumes()
        self.populate_volumes_widget()

    def start_copy(self):
        if not hasattr(self, 'source_dir') or not self.source_dir:
            error_box("No Directory Selected")
            return
        # Save hashing algorithms settings
        hash_algos = self.hashing_algos.buttons()
        for hash_algo in hash_algos:
            self.settings.setValue(hash_algo.text(), hash_algo.isChecked())
        self.settings.sync()

        # Launch Copy
        hash_algos = [hash_algo.text() for hash_algo in self.hashing_algos.buttons() if hash_algo.isChecked()]
        dst_volumes = [item.data(256).rootPath() for item in self.volumes_list.selectedItems() if
                       not item.data(256).isReadOnly() and item.data(256).bytesFree() > self.dir_size]
        if dst_volumes:
            # At least one drive selected and writable
            progress = ProgressWindow(self.source_dir, dst_volumes, hash_algos, self.files_count, self.dir_size)
            progress.setWindowFlags(QtCore.Qt.CustomizeWindowHint)
            progress.setModal(True)
            progress.exec_()
            # copy_files(self.source_dir, dst_volumes, hash_algos)
        else:
            error_box("No Writable/Valid Drive Selected!")

    def init_hashing_widgets(self):
        # Hash Related Widgets
        hash_algos = {
            'md5': None,
            'sha1': None,
            'sha256': None,
        }
        for hash_algo in hash_algos:
            hash_algos[hash_algo] = self.settings.value(hash_algo) if self.settings.value(
                hash_algo) is not None else True
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

    def open_files(self):
        self.source_dir = self.dir_dialog.getExistingDirectory(self, "Choose Directory to Copy")
        self.dir_label.setText(self.source_dir if self.source_dir else "No Directory Selected")
        if self.source_dir:
            self.get_size()

    def select_all(self):
        self.volumes_list.selectAll()

    def deselect_all(self):
        self.volumes_list.clearSelection()

    def get_size(self):
        # Create Loading Modal
        self.loading = LoadingDialog()
        self.loading.setModal(True)
        self.loading.setWindowFlags(QtCore.Qt.CustomizeWindowHint)
        self.loading.show()

        # Start Calculating size & File count
        self.thread = SizeCalcThread(self.source_dir)
        self.thread.data_ready.connect(self.size_calc_handle, QtCore.Qt.QueuedConnection)
        self.thread.start()

    def size_calc_handle(self, data):
        # Unpack Result
        self.dir_size, self.files_count = data

        self.size_label.setText("{:.2f} GB".format(self.dir_size / 10 ** 9))
        self.files_count_label.setText("{} Files".format(self.files_count))
        self.populate_volumes_widget()

        # Kill Modal View
        self.loading.close()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setCentralWidget(MainWidget())

        self.initMenu()

    def initMenu(self):
        menubar = self.menuBar()
        fileMenu = menubar.addMenu("Hola")
        quit = QtWidgets.QAction("Quit", self)
        quit.triggered.connect(self.close)
        fileMenu.addAction(quit)
