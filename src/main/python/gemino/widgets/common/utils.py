from pathlib import Path
from PySide6 import QtCore


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
