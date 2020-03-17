from fbs_runtime.application_context.PySide2 import ApplicationContext

import sys

################ threads.py ##########################
# (Go figure why fbs isn't packing the app correctly #

from PySide2.QtCore import QThread, Signal

import os
import os.path as path
import errno
import shutil
import hashlib
from threading import Thread, current_thread
from datetime import datetime
from copy import copy
from logging import Logger


class SizeCalcThread(QThread):
    data_ready = Signal(object)

    def __init__(self, folder="."):
        super().__init__()
        self.folder = folder

    def run(self):
        dir_size = 0
        total_files = 0
        for dirpath, dirnames, filenames in os.walk(self.folder):
            for filename in filenames:
                try:
                    filepath = path.join(dirpath, filename)
                    dir_size += path.getsize(filepath)
                    total_files += 1
                except (FileNotFoundError, OSError):
                    pass

        self.data_ready.emit((dir_size, total_files))
        self.quit()


class CopyBuffer(Thread):
    def __init__(self, buffer, file_handler):
        super().__init__()
        self.buffer = buffer
        self.file_handler = file_handler

    def run(self):
        # print("Thread {} - Starting copy to {}".format(current_thread(), self.file_handler.name))
        self.file_handler.write(self.buffer)
        # print("Thread {} - Finished copy to {}".format(current_thread(), self.file_handler.name))


class CopyThread(QThread):

    copy_progress = Signal(object)

    def __init__(self, src: str, destinations: list, hashes: list, total_files: int, total_bytes: int, metadata: list):
        super().__init__()
        self.src = src
        self.destinations = destinations
        self.hashes = hashes
        self.total_files = total_files
        self.file_hashes = {}
        self.total_bytes = total_bytes
        self.metadata = metadata
        self.base_path = path.basename(path.normpath(src)) if path.basename(path.normpath(src)) != '' else '[root]'

    def run(self):
        try:
            self.copy(self.src, self.destinations, self.hashes)
        except Exception as error:
            for dst in self.destinations:
                try:
                    report_file_path = path.join(dst, f'{self.base_path}_copy_report.txt')
                    with open(report_file_path, "a", encoding='utf-8') as report_file:
                        report_file.write(f"ERROR DURING COPY:\n")
                        report_file.write(str(error))
                except FileNotFoundError as error:
                    print(f"Error writing to report: {error}")
                    pass
            self.copy_progress.emit((-1, error))

    def copy(self, src: str, destinations: list, hashes: list):
        print("Copying Files...")

        base_path = self.base_path

        buffer_size = 64 * 1024 * 1024  # Read 64M at a time

        files_hashes = {}  # {filepath: {hash_name:hash_value, ...}, ...}

        start_time = datetime.now()
        for dst in destinations:
            try:
                report_file_path = path.join(dst, f'{base_path}_copy_report.txt')
                with open(report_file_path, "w", encoding='utf-8') as report_file:
                    report_file.write(f"# Gemino Copy Report\n")
                    report_file.write(f"# Gemino v2.1.1\n")
                    report_file.write(f"#####################################################\n\n")

                    report_file.write(f"################## Case Metadata ####################\n")
                    report_file.write(f"Operator: {self.metadata['operator']}\n")
                    report_file.write(f"Intake: {self.metadata['intake']}\n")
                    report_file.write(f"Notes:\n{self.metadata['notes']}\n")
                    report_file.write(f"\n")

                    report_file.write(f"################## Copy Information #################\n")
                    report_file.write(f"Source: {src}\n")
                    report_file.write(f"Destination: {path.join(dst, base_path)}\n")
                    report_file.write(f"Total Files: {self.total_files}\n")
                    report_file.write(f"Size: {self.total_bytes} Bytes (~ {self.total_bytes / 10 ** 9} GB)\n")
                    report_file.write(f"Hashes: {' - '.join(self.hashes)}\n")
                    report_file.write(f"\n")

                    report_file.write(f"################## Copy Report ######################\n")
                    report_file.write(f"Start Time: {start_time.isoformat()}\n")
            except FileNotFoundError as error:
                print(f"Error writing to folder: {error}")
                raise

        filecount = 0
        copied_size = 0
        for dirpath, dirnames, filenames in os.walk(src):
            # dst_folder - Join the destination folder (basename_of_source) with the actual relative path
            rel_path = path.relpath(dirpath, src)
            dst_folder = path.normpath(path.join(base_path, rel_path))

            for dst in destinations:
                try:
                    # Create Paths in destination directory
                    dst_path = path.join(dst, dst_folder)
                    os.makedirs(dst_path, exist_ok=True)
                    shutil.copystat(dirpath, dst_path)

                except FileNotFoundError as error:
                    # If a device is not mounted anymore we will get a FileNotFound Error
                    print("{} is not available anymore! Deleting from destination list!".format(dst))
                    destinations.pop(destinations.index(dst))
                    raise

            for filename in filenames:

                if rel_path == "." and 'gemino.txt' in filename:
                    # Ignore gemino's hash files
                    continue

                filecount += 1

                self.copy_progress.emit(
                    (0, {dst: {'status': 'copy', 'processed_bytes': copied_size, 'processed_files': filecount,
                               'current_file': filename}
                         for dst in
                         self.destinations}))

                src_file_path = path.join(dirpath, filename)
                try:
                    with open(src_file_path, "rb", buffering=0) as src_file:
                        # Open all destination files
                        dst_file_ptrs = {}

                        for dst in destinations:
                            dst_path = path.join(dst, dst_folder)
                            dst_file_path = path.join(dst_path, filename)
                            try:
                                dst_file_ptrs[dst] = open(dst_file_path, "wb", buffering=0)
                            except FileNotFoundError:
                                # Targed not available anymore, remove from list
                                print("{} is not available anymore! Deleting from destination list!".format(dst))
                                destinations.pop(destinations.index(dst))

                        file_hashes = {hash_algo: hashlib.__getattribute__(hash_algo)() for hash_algo in hashes if
                                       hasattr(hashlib, hash_algo)}

                        data = src_file.read(buffer_size)
                        while data:

                            threads = []

                            for hash_algo, hash_buffer in file_hashes.items():
                                # Not threaded because CPU bound
                                # Improving performance would need multiprocesses, we'll deal with it another time
                                hash_buffer.update(data)

                            # Forbid thread termination while we have active buffercopy threads
                            # If not done, the threads will return to a non existing thread and crash the application
                            # (I think)
                            self.setTerminationEnabled(False)

                            for dst, dst_file in dst_file_ptrs.items():
                                thread = CopyBuffer(data, dst_file)  # Threaded Version
                                thread.start()  # Threaded Version
                                threads.append(thread)  # Threaded Version
                                # dst_file.write(data)               # Non Threaded Version

                            for thread in threads:
                                thread.join()

                            # All the spawned threads have exited, allow the termination of this thread again
                            self.setTerminationEnabled(True)

                            copied_size += len(data)
                            self.copy_progress.emit(
                                (0, {dst: {'processed_bytes': copied_size, 'processed_files': filecount,
                                           'status': 'copy', 'current_file': filename} for dst in
                                     self.destinations}))
                            data = src_file.read(buffer_size)

                        # Close open files (src auto closes)

                        for dst, dst_file in dst_file_ptrs.items():
                            try:
                                dst_file.close()
                                shutil.copystat(src_file_path, dst_file.name)
                            except (FileNotFoundError, OSError):
                                print("Lost destination")
                                raise

                        for hash_algo, hash_buffer in file_hashes.items():
                            file_hashes[hash_algo] = hash_buffer.hexdigest()
                except (FileNotFoundError, OSError):
                    # FileNotFoundError if source disconnected and we try to open it
                    # OSError if source disconnected and we try to read from it
                    print("Lost source! (Or permission problem)")
                    raise
                files_hashes[path.normpath(path.join(rel_path, filename))] = file_hashes

        # Write Hash Files
        end_time = datetime.now()
        print("Writing Hash Files...")
        # 2020-03-01 - Disabled writing to source dir by default. Will come back once a checkbox is present.
        # for hash_algo in hashes:
        #     try:
        #         report_file_path = path.join(src, '%s_gemino.txt' % hash_algo)
        #         with open(report_file_path, "w", encoding='utf-8') as hash_file:
        #             hash_file.write(
        #                 "Gemino Hash File\nAlgorithm: {}\nGenerated on: {}\n----------------\n\n".format(
        #                     hash_algo, end_date
        #                 )
        #             )
        #             for file, file_hashes in files_hashes.items():
        #                 hash_file.write("{} - {}\n".format(file_hashes[hash_algo], file))
        #     except FileNotFoundError:
        #         print("Unable to write hash file in source dir, volume not connected anymore.")
        #         raise
        #     except OSError as error:
        #         if error.errno in (errno.EROFS, errno.EACCES):
        #             print("Unable to write hash file in source dir, volume is readonly or insufficient permissions.")
        #         raise

        for dst in destinations:
            try:
                report_file_path = path.join(dst, f'{base_path}_copy_report.txt')
                with open(report_file_path, "a", encoding='utf-8') as report_file:
                    report_file.write(f"End Time: {end_time.isoformat()}\n")
                    report_file.write(f"Duration: {end_time - start_time}\n")
                    report_file.write("\n")
                    report_file.write(f"################## Source Hashes ######################\n")
                    for file, file_hashes in files_hashes.items():
                        hash_values = [file_hashes[hash_algo] for hash_algo in hashes]
                        report_file.write(f"{' - '.join(hash_values)} - {file}\n")
            except FileNotFoundError as error:
                print(f"Error writing to report: {error}")
                raise

            for hash_algo in hashes:
                hash_file_path = path.join(dst, f'{base_path}.{hash_algo}')
                try:
                    with open(hash_file_path, "w", encoding='utf-8') as hash_file:
                        for file, file_hashes in files_hashes.items():
                            hash_file.write(f"{file_hashes[hash_algo]} {file}\n")
                except FileNotFoundError:
                    print("Unable to write hash file in destination dir, volume not connected anymore.")
                    raise

        # Verify Hashes
        print("Verifying Hashes...")
        progress = {dst: {'status': 'idle', 'processed_bytes': 0, 'processed_files': filecount, 'current_file': ''} for
                    dst in destinations}
        for dst in destinations:
            hashed_size = 0
            filecount = 0
            hash_error = 0
            try:
                report_file_path = path.join(dst, f'{base_path}_copy_report.txt')
                with open(report_file_path, "a", encoding='utf-8') as report_file:
                    report_file.write("\n")
                    report_file.write(f"################## Verification Report ######################\n")
                    for filename, file_hashes in files_hashes.items():
                        # Update File Progress
                        filecount += 1
                        progress[dst] = {'status': 'hashing', 'processed_bytes': hashed_size,
                                         'processed_files': filecount,
                                         'current_file': ''}
                        self.copy_progress.emit((1, progress))
                        filepath = path.normpath(path.join(dst, base_path, filename))
                        this_file_error = False
                        with open(filepath, "rb") as file:
                            dst_file_hashes = {hash_algo: hashlib.__getattribute__(hash_algo)() for hash_algo in hashes
                                               if
                                               hasattr(hashlib, hash_algo)}

                            data = file.read(buffer_size)
                            while data:
                                for hash_algo, hash_buffer in dst_file_hashes.items():
                                    # Not threaded because CPU bound
                                    # Improving performance would need multiprocesses, we'll deal with it another time
                                    hash_buffer.update(data)
                                hashed_size += len(data)
                                # Update Byte Progress
                                progress[dst] = {'status': 'hashing', 'processed_bytes': hashed_size,
                                                 'processed_files': filecount, 'current_file': filename}
                                self.copy_progress.emit((1, progress))

                                data = file.read(buffer_size)

                            for hash_algo, hash_buffer in dst_file_hashes.items():
                                dst_file_hashes[hash_algo] = hash_buffer.hexdigest()

                            for hash_algo, file_hash in file_hashes.items():
                                if dst_file_hashes[hash_algo] != file_hash:
                                    print("COPY ERROR - %s HASH for %s file DIFFERS!" % (hash_algo, filename))
                                    progress[dst] = {'status': 'error_hash', 'processed_bytes': hashed_size,
                                                     'processed_files': filecount, 'current_file': filename}
                                    self.copy_progress.emit((1, progress))
                                    hash_error += 1
                        if this_file_error:
                            report_file.write(f"Verification failed for file: {filename}\n")

                    if hash_error:
                        report_file.write(f"Verification failed for {hash_error} files.\n")
                        report_file.write(f"Verification successful for {filecount} files\n")

                    if not hash_error:
                        # Signal the end with no errors of the hash verification for the current volume
                        progress[dst] = {'status': 'done', 'processed_bytes': hashed_size,
                                         'processed_files': filecount, 'current_file': ''}
                        report_file.write(f"Verification successful for {filecount} files\n")
                        self.copy_progress.emit((1, progress))

            except FileNotFoundError as error:
                print(f"Error writing to report: {error}")
                raise

        # Done
        print("Done!")
        self.copy_progress.emit((2, {}))


################ widgets.py ##########################
# (Go figure why fbs isn't packing the app correctly #


from PySide2 import QtWidgets, QtCore, QtGui
import webbrowser

# from .threads import SizeCalcThread, CopyThread


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
        self.__current_status_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.__progress_bar = QtWidgets.QProgressBar()
        self.__current_file_label = QtWidgets.QLabel()
        self.__size_progress_label = QtWidgets.QLabel()
        self.__size_progress_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.__file_progress_label = QtWidgets.QLabel()
        self.__file_progress_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.__open_folder_button = QtWidgets.QPushButton('Open Destination')
        self.__open_folder_button.clicked.connect(self.__open_folder)

        self.__layout_container = QtWidgets.QVBoxLayout()
        self.__layout_first_row = QtWidgets.QHBoxLayout()
        self.__layout_third_row = QtWidgets.QHBoxLayout()
        self.__layout_first_row.addWidget(self.__volume_label)
        self.__layout_first_row.addWidget(self.__current_status_label)
        self.__layout_first_row.addWidget(self.__open_folder_button)
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

    def __open_folder(self):
        webbrowser.open(f'file://{self.__volume_name}')


class ProgressWindow(QtWidgets.QDialog):
    STATUSES = ('copying', 'hashing', 'end', 'cancel')
    DESCRIPTIONS = {
        'copying': 'Writing to Device, hashing source on the fly',
        'hashing': 'Verifying data written to device',
        'end': 'Copy and verification finished',
        'cancel': 'File copy has been interrupted',
    }

    def __init__(self, src: str, dst: list, hash_algos: list, total_files: int, total_bytes: int, metadata: list):
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
        self.thread = CopyThread(src, dst, hash_algos, total_files, total_bytes, metadata)
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
            error_box("Halp! An Error Occurred!", f"Bob is Sad T.T\n\nDetails:\n{progress[1]}")
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

        base_path = path.basename(path.normpath(self.src))
        for dst in self.dst:
            try:
                report_file_path = path.join(dst, f'{base_path}_copy_report.txt')
                with open(report_file_path, "a", encoding='utf-8') as report_file:
                    report_file.write(f"\nUser interrupted copy process at: {datetime.now().isoformat()}")
            except FileNotFoundError as error:
                print(f"Error writing to report: {error}")
                error_box('Error Writing to Report', error)
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
        # Source Dir
        self.src_dir_dialog = QtWidgets.QFileDialog(self)
        self.src_dir_dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        self.src_dir_dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly)
        self.src_dir_dialog_button = QtWidgets.QPushButton("Choose Source Folder")
        self.src_dir_dialog_button.clicked.connect(self.open_files)
        self.src_dir_label = QtWidgets.QLabel("No Directory Selected")
        self.files_count_label = QtWidgets.QLabel("0 Files")
        self.size_label = QtWidgets.QLabel("0 GB")
        # Destination Dir
        self.dst_vbar = QtWidgets.QFrame()
        self.dst_vbar.setFrameShape(QtWidgets.QFrame.VLine)
        self.destinations_label = QtWidgets.QLabel("Destinations:")
        self.dst_dir_dialog = QtWidgets.QFileDialog(self)
        self.dst_dir_dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        self.dst_dir_dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly)
        self.dst_dir_dialog_button = QtWidgets.QPushButton("Choose Destination Folder")
        self.dst_dir_dialog_button.clicked.connect(self.select_dst_folder)
        self.dst_dir_label = QtWidgets.QLabel("No Directory Selected")
        self.dst_dir_information_label = QtWidgets.QLabel("Select a destination folder to view storage details")
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
        self.volumes_list_label = QtWidgets.QLabel("Target Drives:")
        self.volumes_list = QtWidgets.QListWidget(self)
        # Report & Hashing
        self.report_hbar = QtWidgets.QFrame()
        self.report_hbar.setFrameShape(QtWidgets.QFrame.HLine)
        self.operator_name_label = QtWidgets.QLabel("Operator:")
        self.operator_name_text_field = QtWidgets.QLineEdit()
        self.intake_number_label = QtWidgets.QLabel("Inake:")
        self.intake_number_text_field = QtWidgets.QLineEdit()
        self.notes_label = QtWidgets.QLabel("Notes:")
        self.notes_text_field = QtWidgets.QTextEdit()
        self.init_hashing_widgets()

        # Layout Management
        self.layout = QtWidgets.QHBoxLayout()
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
        self.setLayout(self.layout)

        # Init data and fill widgets
        self.dir_size = 0
        self.dst_folder = None
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
                    "{} - {} - {} - {} - {:.2f} GB Free".format(volume.rootPath(),
                                                                volume.name(),
                                                                volume.device().data().decode(),
                                                                volume.fileSystemType().data().decode(),
                                                                volume.bytesFree() / 10 ** 9)
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
        if self.dst_folder:
            dst_folder_storage_info = QtCore.QStorageInfo(self.dst_folder)
            dst_folder_writable = os.access(self.dst_folder, os.W_OK)
            if dst_folder_storage_info.isReady() and dst_folder_writable and dst_folder_storage_info.bytesFree() > self.dir_size:
                dst_volumes.append(self.dst_folder)

        dst_volumes = self.check_existing(dst_volumes)

        if dst_volumes:
            # At least one drive selected and writable
            progress = ProgressWindow(self.source_dir, dst_volumes, hash_algos, self.files_count, self.dir_size,
                                      self.metadata)
            progress.setWindowFlags(QtCore.Qt.CustomizeWindowHint)
            progress.setModal(True)
            progress.exec_()
            # copy_files(self.source_dir, dst_volumes, hash_algos)
        else:
            error_box("No Writable/Valid Drive Selected!")

    def check_existing(self, volumes):
        for i in range(len(volumes)):
            dst_path = os.path.join(volumes[i], os.path.basename(self.source_dir))
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

    def init_hashing_widgets(self):
        # Hash Related Widgets
        hash_algos = {
            'md5': None,
            'sha1': None,
            'sha256': None,
        }
        for hash_algo in hash_algos:
            stored_setting = self.settings.value(hash_algo)
            hash_algos[hash_algo] = bool(stored_setting) if stored_setting is not None else True
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
        self.source_dir = self.src_dir_dialog.getExistingDirectory(self, "Choose Directory to Copy")
        self.src_dir_label.setText(self.source_dir if self.source_dir else "No Directory Selected")
        if self.source_dir:
            self.get_size()

    def select_dst_folder(self):
        self.dst_folder = self.dst_dir_dialog.getExistingDirectory(self, "Choose Directory to Copy")
        self.dst_dir_label.setText(self.dst_folder if self.dst_folder else "No Directory Selected")
        if not self.dst_folder:
            self.dst_dir_information_label.setText("Select a destination folder to view storage details")
        self.dst_folder_check()

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

    def dst_folder_check(self):
        if self.dst_folder:
            # Only execute if a destination folder has been selected
            dst_storage_info = QtCore.QStorageInfo(self.dst_folder)
            dst_bytes_available = dst_storage_info.bytesAvailable()
            dst_folder_writable = os.access(self.dst_folder, os.W_OK)
            if dst_bytes_available > self.dir_size:
                # Enough space available on destination
                self.dst_dir_information_label.setText("Enough space available on destination")
            else:
                self.dst_dir_information_label.setText("NOT Enough space available on destination")

            if dst_folder_writable and dst_storage_info.bytesFree() > self.dir_size:
                self.dst_dir_information_label.setText(
                    "On volume: {} - {} - {:.2f} GB Free".format(dst_storage_info.name(),
                                                                 dst_storage_info.fileSystemType().data().decode(),
                                                                 dst_storage_info.bytesFree() / 10 ** 9))
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
                        dst_storage_info.bytesFree() / 10 ** 9,
                        ", ".join(errors))
                )
                # self.dst_dir_information_label.setTextColor(QtGui.QColor(255, 0, 0))

    @property
    def metadata(self):
        return {
            'operator': self.operator_name_text_field.text(),
            'intake': self.intake_number_text_field.text(),
            'notes': self.notes_text_field.toPlainText(),
        }

    def confirm_overwrite(self, path):
        confirmation = QtWidgets.QMessageBox()
        choice = confirmation.question(self, 'Confirm Overwrite',
                                       f'Directory: {path} is not empty.\nData contained may be overwritten without additional confirmation.\n\nDo you want to continue?',
                                       QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
        if choice == QtWidgets.QMessageBox.Yes:
            return True
        else:
            return False


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, version):
        super().__init__()

        self.setCentralWidget(MainWidget())
        self.initMenu()
        self.version = version

    def initMenu(self):
        bar = self.menuBar()
        self.help = bar.addMenu("Help")
        self.about = QtWidgets.QAction("About")
        self.about.triggered.connect(self.about_box)
        self.help.addAction(self.about)

    def about_box(self):
        message = QtWidgets.QMessageBox()
        message.setIcon(QtWidgets.QMessageBox.Information)
        message.setText("gemino")
        message.setInformativeText(
            "gemino file duplicator\n\nv{} - January 2019\n\nDeveloped with ❤️ by Francesco Servida during the work at:\n - University of Lausanne\n - United Nations Investigative Team for Accountability of crimes committed by Da’esh/ISIL (UNITAD)\n\nLicensed under GPLv3\nhttps://opensource.org/licenses/GPL-3.0".format(
                self.version))
        message.setWindowTitle("About")
        message.setStandardButtons(QtWidgets.QMessageBox.Ok)
        message.exec_()


################ main.py #############################
# (Go figure why fbs isn't packing the app correctly #


class AppContext(ApplicationContext):  # 1. Subclass ApplicationContext
    def run(self):  # 2. Implement run()
        version = self.build_settings['version']
        window = MainWindow(version)
        window.setWindowTitle("gemino v" + version)
        window.resize(650, 600)
        window.show()
        return self.app.exec_()  # 3. End run() with this line


if __name__ == '__main__':
    appctxt = AppContext()  # 4. Instantiate the subclass
    exit_code = appctxt.run()  # 5. Invoke run()
    sys.exit(exit_code)
