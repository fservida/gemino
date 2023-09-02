from PySide2.QtCore import QThread, Signal

import os
import os.path as path
import hashlib
from datetime import datetime
import shutil
import uuid

from pyaff4 import container
from pyaff4 import lexicon, logical, escaping
from pyaff4 import rdfvalue, utils
from pyaff4 import hashes as aff4_hashes
from pyaff4 import data_store, linear_hasher

from ..utils import CopyBuffer
from .aff4 import LinearVerificationListener, trimVolume, ProgressContextListener


# TODO - Split CopyThread in Two Subclasses for basic and aff4 (and maybe others).
class CopyThread(QThread):
    copy_progress = Signal(object)

    def __init__(self, src: str, destinations: list, hashes: list, total_files: int, total_bytes: int, metadata: list, aff4: bool, aff4_filename: str):
        super().__init__()
        self.src = src
        self.destinations = destinations
        self.hashes = hashes
        self.total_files = total_files
        self.file_hashes = {}
        self.total_bytes = total_bytes
        self.metadata = metadata
        self.aff4 = bool(aff4)
        self.aff4_filename = str(aff4_filename)
        if self.aff4:
            self.base_path = self.aff4_filename
        else:
            self.base_path = path.basename(path.normpath(src)) if path.basename(path.normpath(src)) != '' else '[root]'
        print(self.aff4, self.aff4_filename, self.destinations)

    def run(self):
        try:
            if self.aff4:
                self.copy_aff4(self.src, self.destinations, self.hashes)
            else:
                self.copy_folder(self.src, self.destinations, self.hashes)
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
            raise
            self.copy_progress.emit((-1, error))

    def copy_folder(self, src: str, destinations: list, hashes: list):
        print("Copying Files...")

        base_path = self.base_path

        buffer_size = 64 * 1024 * 1024  # Read 64M at a time

        files_hashes = {}  # {filepath: {hash_name:hash_value, ...}, ...}

        start_time = self.initialize_log_files(destinations, base_path, src)

        filecount = 0
        copied_size = 0
        for dirpath, dirnames, filenames in os.walk(src):
            # dst_folder - Join the destination folder (basename_of_source) with the actual relative path
            rel_path = path.relpath(dirpath, src)
            dst_folder = path.normpath(path.join(base_path, rel_path))

            # Create Paths in destination directory
            for dst in destinations:
                try:
                    dst_path = path.join(dst, dst_folder)
                    os.makedirs(dst_path, exist_ok=True)
                    try:
                        shutil.copystat(dirpath, dst_path)
                    except OSError:
                        # shutil failed to copy directory metadata. Not a critical error, log and continue.
                        print(
                            f"Warning - Unable to copy directory attributes to destination folder ({dst_path}), timestamps will not reflect the source.")
                        # TODO - Insert code to log (and display) this warning, eventually a UI for the user to confirm could be added.

                except FileNotFoundError as error:
                    # If a device is not mounted anymore we will get a FileNotFound Error
                    print("{} is not available anymore! Deleting from destination list!".format(dst))
                    destinations.pop(destinations.index(dst))
                    raise

            # Copy Files
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
        self.copy_progress.emit((1, progress))
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

    def copy_aff4(self, src: str, destinations: list, hashes: list):

        assert len(destinations) == 1
        destination = destinations[0]

        print("Copying Files...")

        base_path = self.base_path

        # buffer_size = 64 * 1024 * 1024  # Read 64M at a time

        files_hashes = {}  # {filepath: {hash_name:hash_value, ...}, ...}

        start_time = self.initialize_log_files(destinations, base_path, src)

        # Initialize AFF4 Resolver and Container
        container_path = path.join(destination, self.base_path)
        with data_store.MemoryDataStore() as resolver:
            container_urn = rdfvalue.URN.FromFileName(container_path)
            with container.Container.createURN(resolver, container_urn, encryption=False, zip_based=True, compression_method=lexicon.AFF4_IMAGE_COMPRESSION_STORED) as volume:
                hashers_algos = []
                if "md5" in hashes:
                    hashers_algos.append(lexicon.HASH_MD5)
                if "sha1" in hashes:
                    hashers_algos.append(lexicon.HASH_SHA1)
                if "sha256" in hashes:
                    hashers_algos.append(lexicon.HASH_SHA256)

                # Read Files and Folder and add to containers
                filecount = 0
                copied_size = 0

                resolver.Set(volume.urn, volume.urn, rdfvalue.URN('http://aff4.org/Schema#caseName'),
                                 rdfvalue.XSDString(utils.SmartUnicode(self.metadata['intake'])))
                resolver.Set(volume.urn, volume.urn, rdfvalue.URN('http://aff4.org/Schema#caseDescription'),
                             rdfvalue.XSDString(utils.SmartUnicode(self.metadata['notes'])))
                resolver.Set(volume.urn, volume.urn, rdfvalue.URN('http://aff4.org/Schema#examiner'),
                             rdfvalue.XSDString(utils.SmartUnicode(self.metadata['operator'])))
                resolver.Add(volume.urn, volume.urn, rdfvalue.URN(lexicon.AFF4_TYPE),
                             rdfvalue.URN('http://aff4.org/Schema#CaseDetails'))
                resolver.Set(volume.urn, volume.urn, rdfvalue.URN('http://aff4.org/Schema#startTime'),
                             rdfvalue.XSDDateTime(utils.SmartUnicode(start_time.isoformat())))
                resolver.Add(volume.urn, volume.urn, rdfvalue.URN(lexicon.AFF4_TYPE),
                             rdfvalue.URN('http://aff4.org/Schema#TimeStamps'))

                for dirpath, dirnames, filenames in os.walk(src):
                    # dst_folder - Join the destination folder (basename_of_source) with the actual relative path
                    rel_path = path.relpath(dirpath, src)
                    aff4_tree_path = path.normpath(path.join(path.basename(src), rel_path))

                    # Create Paths in destination directory
                    # For AFF4 containers
                    # We want the DST Pathname as the source pathname relative to the source top directory
                    dst_path = aff4_tree_path
                    pathname = utils.SmartUnicode(dst_path)
                    fsmeta = logical.FSMetadata.create(dirpath)  # We need the absolute path to get FS Metadata
                    if volume.isAFF4Collision(pathname):
                        image_urn = rdfvalue.URN("aff4://%s" % uuid.uuid4())
                    else:
                        image_urn = volume.urn.Append(escaping.arnPathFragment_from_path(pathname), quote=False)
                    fsmeta.urn = image_urn
                    fsmeta.store(resolver)
                    resolver.Set(volume.urn, image_urn, rdfvalue.URN(lexicon.standard11.pathName),
                                 rdfvalue.XSDString(pathname))
                    resolver.Add(volume.urn, image_urn, rdfvalue.URN(lexicon.AFF4_TYPE),
                                 rdfvalue.URN(lexicon.standard11.FolderImage))
                    resolver.Add(volume.urn, image_urn, rdfvalue.URN(lexicon.AFF4_TYPE),
                                 rdfvalue.URN(lexicon.standard.Image))

                    # Copy Files
                    for filename in filenames:

                        filecount += 1

                        self.copy_progress.emit(
                            (0, {dst: {'status': 'copy', 'processed_bytes': copied_size, 'processed_files': filecount,
                                       'current_file': filename}
                                 for dst in
                                 self.destinations}))

                        src_file_path = path.join(dirpath, filename)
                        src_file_path_rel = path.join(aff4_tree_path, filename)
                        pathname = utils.SmartUnicode(src_file_path_rel)  # Destination filepath is relative to top source dir
                        fsmeta = logical.FSMetadata.create(src_file_path)  # FSMetadata needs absolute path for source info
                        try:
                            filesize = path.getsize(src_file_path)  # Needed until I find a way to get signaled on AFF4's copied size per file.
                            with open(src_file_path, "rb", buffering=0) as src_file:
                                file_hashes = {hash_algo: "" for hash_algo in hashes}
                                hasher = linear_hasher.StreamHasher(src_file, hashers_algos)
                                progress = ProgressContextListener()
                                progress.start = copied_size
                                progress.destinations = self.destinations
                                progress.processed_files = filecount
                                progress.current_file = filename
                                progress.copy_progress = self.copy_progress
                                progress.status = 'copy'
                                urn = volume.writeLogicalStream(pathname, hasher, fsmeta.length,
                                                                allow_large_zipsegments=True, progress=progress)
                                fsmeta.urn = urn
                                fsmeta.store(resolver)
                                for h in hasher.hashes:
                                    hh = aff4_hashes.newImmutableHash(h.hexdigest(), hasher.hashToType[h])
                                    resolver.Add(urn, urn, rdfvalue.URN(lexicon.standard.hash), hh)
                                    file_hashes[h.name] = hh.value
                            copied_size += filesize

                        except (FileNotFoundError, OSError):
                            # FileNotFoundError if source disconnected and we try to open it
                            # OSError if source disconnected and we try to read from it
                            print("Lost source! (Or permission problem)")
                            raise
                        files_hashes[path.normpath(path.join(rel_path, filename))] = file_hashes

                # Write Hash Files
                end_time = datetime.now()

                resolver.Set(volume.urn, volume.urn, rdfvalue.URN('http://aff4.org/Schema#endTime'),
                             rdfvalue.XSDDateTime(utils.SmartUnicode(end_time.isoformat())))


        print("Writing Hash Files...")

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

        # Verify Hashes
        print("Verifying Hashes...")
        progress = {dst: {'status': 'idle', 'processed_bytes': 0, 'processed_files': filecount, 'current_file': ''} for
                    dst in destinations}
        self.copy_progress.emit((1, progress))
        for dst in destinations:
            hashed_size = 0
            filecount = 0
            try:
                report_file_path = path.join(dst, f'{base_path}_copy_report.txt')
                with open(report_file_path, "a", encoding='utf-8') as report_file:
                    report_file.write("\n")
                    report_file.write(f"################## Verification Report ######################\n")
                    with container.Container.openURNtoContainer(rdfvalue.URN.FromFileName(container_path)) as volume:
                        resolver = volume.resolver
                        verification_listener = LinearVerificationListener(volume.urn)
                        hasher = linear_hasher.LinearHasher2(resolver, verification_listener)

                        for image in volume.images():
                            # Each image is a file in the container.
                            # Update Byte Progress
                            filecount += 1
                            filesize = int(image.resolver.store.get(image.urn).get(lexicon.AFF4_STREAM_SIZE))
                            filename = trimVolume(volume.urn, image.urn)
                            progress[dst] = {'status': 'hashing', 'processed_bytes': hashed_size,
                                             'processed_files': filecount,
                                             'current_file': filename}
                            self.copy_progress.emit((1, progress))

                            # Quick Fix, will not work if multiple destinations are implemented
                            progress_listener = ProgressContextListener()
                            progress_listener.start = hashed_size
                            progress_listener.destinations = self.destinations
                            progress_listener.processed_files = filecount
                            progress_listener.current_file = filename
                            progress_listener.copy_progress = self.copy_progress
                            progress_listener.status = 'hashing'

                            hasher.hash(image, progress=progress_listener)
                            hashed_size += filesize

                        if verification_listener.failed:
                            failed_files = len(verification_listener.failed)
                            progress[dst] = {'status': 'error_hash', 'processed_bytes': hashed_size,
                                             'processed_files': filecount, 'current_file': ''}
                            for file in verification_listener.failed:
                                report_file.write(f"Verification failed for file: {trimVolume(volume.urn, file)}\n")
                                for hash_failed in verification_listener.failed[file]:
                                    report_file.write(f"\t{hash_failed[0]} Hash Differs - Stored: {hash_failed[1]} - Calculated {hash_failed[2]}\n")
                            report_file.write(f"Verification failed for {failed_files} files.\n")
                            report_file.write(f"Verification successful for {filecount-failed_files} files\n")
                            self.copy_progress.emit((1, progress))

                        if not verification_listener.failed:
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

    def initialize_log_files(self, destinations, base_path, src):
        start_time = datetime.now()
        for dst in destinations:
            try:
                report_file_path = path.join(dst, f'{base_path}_copy_report.txt')
                with open(report_file_path, "w", encoding='utf-8') as report_file:
                    report_file.write(f"# Gemino Copy Report\n")
                    report_file.write(f"# Gemino v2.5.2\n")
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
        return start_time