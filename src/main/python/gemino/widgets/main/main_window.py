from PySide6 import QtWidgets, QtCore, QtGui
import traceback

from .main_widget import MainWidget
from ..common.loading_window import LoadingWindow
from ..viewer import AdvancedWidget
from ..common import ProgressWindow, error_box
from ...threads.aff4 import GetSummaryThread, OpenContainerThread
from ...threads.aff4.utils import number_of_items


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
        self.loading: LoadingWindow = None

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
            f"gemino\n\nForensic logical imager and file duplicator\n\nv{self.version}\n\nDeveloped with ❤️ by Francesco Servida.\n\nLicensed under GPLv3\nhttps://opensource.org/licenses/GPL-3.0\nThird party dependencies: https://francescoservida.ch/gemino/LICENSES"
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
                # Get number of items in AFF4-L container to display progress bar
                # Fast iteration using zipfile library
                item_count = number_of_items(src_container_path)
                self.loading = LoadingWindow(
                    parent=self,
                    total_items=item_count,
                    call_thread=OpenContainerThread(src_container_path),
                    return_function=self.advanced_widget.populate,
                )
                self.loading.setWindowFlags(
                    QtCore.Qt.CustomizeWindowHint | QtCore.Qt.Dialog
                )
                self.loading.setModal(True)
                self.loading.setWindowModality(QtCore.Qt.ApplicationModal)
                self.loading.open()
                self.loading.start_tasks()
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

    def verify_aff4_start(self, total_files, total_size, src_container_path):
        self.progress = ProgressWindow(
            self,
            src_container_path,
            total_files=total_files,
            total_bytes=total_size,
            aff4_verify=True,
        )
        self.progress.setWindowFlags(QtCore.Qt.CustomizeWindowHint | QtCore.Qt.Dialog)
        self.progress.setModal(True)
        self.progress.setWindowModality(QtCore.Qt.ApplicationModal)
        self.progress.open()
        self.progress.start_tasks()

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
                item_count = number_of_items(src_container_path)
                self.loading = LoadingWindow(
                    parent=self,
                    total_items=item_count,
                    call_thread=GetSummaryThread(src_container_path),
                    return_function=self.verify_aff4_start,
                )
                self.loading.setWindowFlags(
                    QtCore.Qt.CustomizeWindowHint | QtCore.Qt.Dialog
                )
                self.loading.setModal(True)
                self.loading.setWindowModality(QtCore.Qt.ApplicationModal)
                self.loading.open()
                self.loading.start_tasks()
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
