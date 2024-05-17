from PySide6 import QtWidgets, QtCore


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
