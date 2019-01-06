from PySide2.QtCore import QThread, Signal

import os
import os.path as path
import errno
import shutil
import hashlib
from threading import Thread, current_thread
from datetime import datetime


class SizeCalcThread(QThread):
    data_ready = Signal(object)

    def __init__(self, folder="."):
        super().__init__()
        self.folder = folder

    def run(self):
        dir_size = 0
        total_files = 0
        for dirpath, dirnames, filenames in os.walk(self.folder):
            rel_path = path.relpath(dirpath, self.folder)

            for filename in filenames:

                if rel_path == "." and 'gemino.txt' in filename:
                    # Ignore gemino's hash files (only if in root directory, as we're going to replace them)
                    continue

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

    def __init__(self, src: str, destinations: list, hashes: list, total_files: int):
        super().__init__()
        self.src = src
        self.destinations = destinations
        self.hashes = hashes
        self.total_files = total_files
        self.file_hashes = {}

    def run(self):
        try:
            self.copy(self.src, self.destinations, self.hashes)
        except Exception as error:
            self.copy_progress.emit((-1, error))

    def copy(self, src: str, destinations: list, hashes: list):
        print("Copying Files...")
        base_path = path.basename(path.normpath(src))

        buffer_size = 64 * 1024 * 1024  # Read 64M at a time

        files_hashes = {}  # {filepath: {hash_name:hash_value, ...}, ...}

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

            for filename in filenames:

                if rel_path == "." and 'gemino.txt' in filename:
                    # Ignore gemino's hash files
                    continue

                filecount += 1

                self.copy_progress.emit(
                    (0, {dst: {'status': 'copy', 'processed_bytes': copied_size, 'processed_files': filecount, 'current_file': filename}
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
                    print("Lost source!")
                    raise IOError("It seems like we lost access to the source... Bob is sad :-(")
                files_hashes[path.normpath(path.join(rel_path, filename))] = file_hashes

        #print("Total Copied Bytes: %s" % copied_size)

        # Write Hash Files
        end_date = datetime.now().isoformat()
        print("Writing Hash Files...")
        for hash_algo in hashes:
            try:
                hash_file_path = path.join(src, '%s_gemino.txt' % hash_algo)
                with open(hash_file_path, "w") as hash_file:
                    hash_file.write(
                        "Gemino Hash File\nAlgorithm: {}\nGenerated on: {}\n----------------\n\n".format(
                            hash_algo, end_date
                        )
                    )
                    for file, file_hashes in files_hashes.items():
                        hash_file.write("{} - {}\n".format(file_hashes[hash_algo], file))
            except FileNotFoundError:
                print("Unable to write hash file in source dir, volume not connected anymore.")
                raise
            except OSError as error:
                if error.errno in (errno.EROFS, errno.EACCES):
                    print("Unable to write hash file in source dir, volume is readonly or insufficient permissions.")
                else:
                    raise

        for dst in destinations:
            dst_folder = path.normpath(path.join(dst, base_path))
            for hash_algo in hashes:
                hash_file_path = path.join(dst_folder, '%s_gemino.txt' % hash_algo)
                try:
                    with open(hash_file_path, "w") as hash_file:
                        hash_file.write(
                            "Gemino Hash File\nAlgorithm: {}\nGenerated on: {}\n----------------\n\n".format(
                                hash_algo, end_date
                            )
                        )
                        for file, file_hashes in files_hashes.items():
                            hash_file.write("{} - {}\n".format(file_hashes[hash_algo], file))
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
            hash_error = False
            for filename, file_hashes in files_hashes.items():
                # Update File Progress
                filecount += 1
                progress[dst] = {'status': 'hashing', 'processed_bytes': hashed_size, 'processed_files': filecount,
                                 'current_file': ''}
                self.copy_progress.emit((1, progress))
                filepath = path.normpath(path.join(dst, base_path, filename))
                with open(filepath, "rb") as file:
                    dst_file_hashes = {hash_algo: hashlib.__getattribute__(hash_algo)() for hash_algo in hashes if
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
                            hash_error = True

                if hash_error:
                    # Terminate file verification for current volume if a single hash is not valid
                    break
            if not hash_error:
                # Signal the end with no errors of the hash verification for the current volume
                progress[dst] = {'status': 'done', 'processed_bytes': hashed_size,
                                 'processed_files': filecount, 'current_file': ''}
                self.copy_progress.emit((1, progress))

        # Done
        print("Done!")
        self.copy_progress.emit((2, {}))
