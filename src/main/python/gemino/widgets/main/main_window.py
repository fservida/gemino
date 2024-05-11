from PySide6 import QtWidgets, QtCore, QtGui
import traceback

from .main_widget import MainWidget
from ..viewer import AdvancedWidget
from ..common import ProgressWindow, error_box
from ...threads.copy.logical.aff4 import get_metadata, get_container_summary


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
