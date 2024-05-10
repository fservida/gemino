import io
import os.path
import traceback
from dataclasses import dataclass
from typing import Union
import puremagic
from puremagic import PureError
from PySide6 import QtWidgets, QtCore, QtGui, QtPdf
from PySide6.QtPdfWidgets import QPdfView
from pathlib import Path
from PIL import Image, ImageQt, ExifTags

from pyaff4.container import (
    PhysicalImageContainer,
    WritableHashBasedImageContainer,
    LogicalImageContainer,
    PreStdLogicalImageContainer,
    EncryptedImageContainer,
)
from pyaff4 import lexicon, rdfvalue

from ..copy.logical.aff4 import AFF4Item


@dataclass
class Exif:
    name: str
    value: str


class HexDumpWidget(QtWidgets.QPlainTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.verticalScrollBar().sliderMoved.connect(self.preload_on_scrollbar_change)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.setFont(font)

        self.current_file = None
        self.loaded_data = 0

    def reset(self):
        self.current_file = None
        self.loaded_data = 0
        self.clear()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.adjust_scrollbar()

    def scrollContentsBy(self, dx, dy):
        # self.load_next_chunk()
        super().scrollContentsBy(dx, dy)

    def get_scrollbar_settings(self):
        BOTTOM_MARGIN = 1
        widget_height = self.height()
        # font_size = self.hex_viewer.fontMetrics().height()
        font_size = 12
        lines_per_page = int(round(widget_height / font_size))
        bytes_per_line = 16
        total_lines = (
            self.current_file.Length() / bytes_per_line if self.current_file else 0
        )
        scrollbar_max_lines = total_lines - lines_per_page + BOTTOM_MARGIN
        return scrollbar_max_lines, lines_per_page

    def load_next_chunk(self):
        chunk_size = 1024  # Adjust chunk size as needed
        file_size = self.current_file.Length()
        if self.loaded_data < file_size:
            self.current_file.seek(self.loaded_data)
            chunk = self.current_file.Read(chunk_size)
            hex_dump = self.format_hex_dump(chunk, self.loaded_data)
            self.insertPlainText(hex_dump + "\n")
            self.adjust_scrollbar()
            self.loaded_data += len(chunk)

    def adjust_scrollbar(self):
        scrollbar = self.verticalScrollBar()
        scrollbar_range, scrollbar_step = self.get_scrollbar_settings()
        scrollbar.setRange(0, scrollbar_range)
        scrollbar.setPageStep(scrollbar_step)

    def preload_on_scrollbar_change(self):
        scrollbar = self.verticalScrollBar()
        scrollbar_range, scrollbar_step = self.get_scrollbar_settings()
        print(
            scrollbar.value(),
            scrollbar.maximum(),
            scrollbar_range,
            self.loaded_data,
            self.height(),
        )
        bytes_per_line = 16
        while (
            scrollbar.value()
            and (
                (scrollbar.value() + scrollbar_step) * bytes_per_line
                >= self.loaded_data
            )
            and self.loaded_data < self.current_file.Length()
        ):
            self.load_next_chunk()

    @staticmethod
    def format_hex_dump(data, offset):
        BYTES_PER_LINE = 16
        formatted_text = ""
        for i in range(0, len(data), BYTES_PER_LINE):
            chunk = data[i : i + BYTES_PER_LINE]
            chunk_len = len(chunk)
            hex_line = f"{offset + i:010X} | "
            ascii_line = ""
            for b in chunk:
                hex_line += f" {b:02X}"
                ascii_line += chr(b) if 32 <= b < 127 else "."
            if chunk_len < BYTES_PER_LINE:
                for _ in range(0, BYTES_PER_LINE-chunk_len):
                    hex_line += f"   "  # 3 empty spaces: a spacer, and 2 to match missing 00
            formatted_text += f"{hex_line}   {ascii_line}\n"
        return formatted_text.rstrip("\n")


class AdvancedWidget(QtWidgets.QWidget):
    def __init__(
        self,
        parent: QtWidgets.QWidget = None,
    ):
        super().__init__(parent=parent)

        self.volume = None
        self.aff4_items = None

        # Instantiate Widgets
        ## Top
        self.open_button = QtWidgets.QPushButton("Open AFF4-L Container")
        self.container_label = QtWidgets.QLabel()

        self.top_buttons_layout = QtWidgets.QHBoxLayout()
        self.top_buttons_layout.addWidget(self.open_button)
        self.top_buttons_layout.addWidget(self.container_label)
        self.top_buttons_layout.addStretch()

        ## Directory view
        self.tree_view = QtWidgets.QTreeWidget()

        ## Bottom
        self.container_details_button = QtWidgets.QPushButton("View Container Metadata")
        self.container_details_button.clicked.connect(self.show_case_metadata)
        self.container_details_button.setDisabled(True)

        self.export_button = QtWidgets.QPushButton("Export Selected File")
        self.export_button.clicked.connect(self.export)
        self.export_button.setDisabled(True)

        self.bottom_buttons_layout = QtWidgets.QHBoxLayout()
        self.bottom_buttons_layout.addWidget(self.container_details_button)
        self.bottom_buttons_layout.addWidget(self.export_button)
        self.bottom_buttons_layout.addStretch()

        ## Hex Viewer
        self.hex_viewer = HexDumpWidget()

        ## Image label
        self.image_label = QtWidgets.QLabel()

        ## Text edit
        self.text_edit = QtWidgets.QTextEdit()
        self.text_edit.setReadOnly(True)  # Set readonly

        ## PDF View
        self.pdf_view = QPdfView()
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)

        # Initially hide all widgets, Keep text edit always to keep layout uniform
        self.image_label.hide()
        self.pdf_view.hide()

        ## Layout Management
        self.window_layout = QtWidgets.QVBoxLayout()
        self.window_layout.addLayout(self.top_buttons_layout)

        self.window_layout.addWidget(self.tree_view)

        self.bottom_view_tabs = QtWidgets.QTabWidget()

        self.viewer_tab = QtWidgets.QWidget()
        self.metadata_tab = QtWidgets.QWidget()

        self.viewer_layout = QtWidgets.QHBoxLayout()
        self.viewer_layout.addWidget(self.hex_viewer)
        self.viewer_layout.addWidget(self.image_label)
        self.viewer_layout.addWidget(self.text_edit)
        self.viewer_layout.addWidget(self.pdf_view)
        self.viewer_tab.setLayout(self.viewer_layout)

        # Layout and Widget shenanigans to ensure it matches margins of viewer tab
        self.metadata_box = QtWidgets.QTextEdit()
        self.metadata_layout = QtWidgets.QHBoxLayout()
        self.metadata_layout.addWidget(self.metadata_box)
        self.metadata_tab.setLayout(self.metadata_layout)

        self.bottom_view_tabs.addTab(self.viewer_tab, "Content")
        self.bottom_view_tabs.addTab(self.metadata_tab, "Metadata")

        self.window_layout.addWidget(self.bottom_view_tabs)
        self.window_layout.addLayout(self.bottom_buttons_layout)

        self.setLayout(self.window_layout)

        ## Prepare TreeWidget
        self.tree_view.setColumnCount(3)
        self.tree_view.setHeaderLabels(
            ["Name", "Modified", "Created", "Size", "Folder", "URN"]
        )
        self.tree_view.setSortingEnabled(True)
        # Folder and URN columns are not needed in display.
        self.tree_view.hideColumn(4)
        self.tree_view.hideColumn(5)

        self.tree_view.header().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents
        )
        self.tree_view.itemSelectionChanged.connect(self.view_details)

    def populate(
        self,
        aff4_volume: Union[
            PhysicalImageContainer,
            WritableHashBasedImageContainer,
            LogicalImageContainer,
            PreStdLogicalImageContainer,
            EncryptedImageContainer,
        ],
        aff4_items: dict[str, AFF4Item],
        src_container_path: str,
    ):
        self.volume = aff4_volume

        # We need to disconnect before clearing the tree,
        # else the selection changes and view_details is called on an empty tree
        self.tree_view.itemSelectionChanged.disconnect(self.view_details)
        self.tree_view.clear()
        self.tree_view.itemSelectionChanged.connect(self.view_details)
        self.hex_viewer.reset()
        self.image_label.clear()
        self.text_edit.clear()
        self.pdf_view.setDocument(None)
        self.metadata_box.clear()

        self.container_label.setText(src_container_path)
        self.container_details_button.setEnabled(True)

        # Populate tree
        items = []
        item_dict: dict[Path, QtWidgets.QTreeWidgetItem] = {}

        # This relies on the dictionary being already sorted by key (path)
        for path, item in aff4_items.items():
            current_item_path = Path(str(path).lstrip("/"))
            if current_item_path.parent == Path(""):
                # Top Level Node
                parent = None
            else:
                try:
                    parent = item_dict[current_item_path.parent]
                except KeyError:
                    # Parent does not exist (eg. in AFF4-L reference images), create all needed tree items
                    self.create_missing_tree_folders(
                        current_item_path.parent, items, item_dict
                    )
                    parent = item_dict[current_item_path.parent]
            qtree_item = QtWidgets.QTreeWidgetItem(
                parent,
                [
                    item.path.split("/")[-1],
                    item.modify,
                    item.create,
                    str(item.size),
                    str(item.folder),
                    str(item.urn),
                ],
            )
            item_dict[current_item_path] = qtree_item
            items.append(qtree_item)

        self.tree_view.insertTopLevelItems(0, items)

    @staticmethod
    def create_missing_tree_folders(
        current_item_path: Path,
        items: list,
        item_dict: dict[Path, QtWidgets.QTreeWidgetItem],
    ):
        ancestors = current_item_path.parts
        for i in range(len(ancestors)):
            ancestor = ancestors[i]
            ancestor_full_path = os.path.join(*ancestors[: i + 1])
            # Check if item exist already, and create only if missing
            ancestor_path = Path(ancestor_full_path)
            if not item_dict.get(ancestor_path, None):
                if ancestor_path.parent == Path(""):
                    parent = None
                else:
                    # We are lower in the loop, the parent should have been created already by the preceding iteration
                    parent = item_dict[ancestor_path.parent]
                qtree_item = QtWidgets.QTreeWidgetItem(
                    parent, [ancestor, "", "", "", "True", ""]
                )  # True is "Folder"
                item_dict[ancestor_path] = qtree_item
                items.append(qtree_item)

    def export(self):
        if self.current_file is not None:

            self.export_dst = QtWidgets.QFileDialog(self)
            self.export_dst.setWindowTitle("Export File as")
            self.export_dst.setWindowModality(QtCore.Qt.WindowModal)
            directory = ""
            try:
                directory = QtCore.QStandardPaths.standardLocations(
                    QtCore.QStandardPaths.HomeLocation
                )[0]
            except:
                pass
            filename = self.tree_view.selectedItems()[0].data(0, 0)
            self.export_dst.setDirectory(os.path.join(directory, filename))
            self.export_dst.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
            accepted = self.export_dst.exec()
            export_dst_path: str = None
            if accepted:
                export_dst_path = self.export_dst.selectedFiles()[0]
            if export_dst_path:
                print(f"We shall export the selected item to: {export_dst_path}")
                with open(export_dst_path, "wb") as dst_file:
                    self.current_file.seek(0)
                    dst_file.write(self.current_file.ReadAll())
                    print("Finished writing file")
        pass

    def view_details(self):
        urn = self.tree_view.selectedItems()[0].data(5, 0)
        folder = self.tree_view.selectedItems()[0].data(4, 0) == "True"

        # Clear interface
        self.hex_viewer.clear()
        self.image_label.clear()
        self.text_edit.clear()
        self.pdf_view.setDocument(None)
        self.metadata_box.clear()
        self.image_label.hide()
        self.text_edit.hide()
        self.pdf_view.hide()
        self.export_button.setDisabled(True)
        self.load_metadata(urn, folder)
        if folder:
            self.text_edit.show()
        if not folder:
            self.export_button.setDisabled(False)
            self.current_file = self.hex_viewer.current_file = (
                self.volume.resolver.AFF4FactoryOpen(urn, version=self.volume.version)
            )
            self.hex_viewer.loaded_data = 0
            header = self.current_file.Read(4096)
            try:
                filename = self.volume.resolver.Get(
                    self.volume.urn, urn, rdfvalue.URN(lexicon.standard11.pathName)
                )[0]
                try:
                    mime_type = puremagic.magic_string(header, filename)[0].mime_type
                except PureError as e:
                    mime_type = None
                    if Path(str(filename)).suffix in (".csv", ".tsv"):
                        # In future use something like https://oss.sheetjs.com/ to handle preview, including xlsx
                        mime_type = "text/plain"
                    elif self.is_plain_text(header):
                        mime_type = "text/plain"
                if mime_type.startswith("application") and not mime_type == "application/pdf":
                    # prepend text to all other mimetypes if we heuristically suppose plain text support
                    if self.is_plain_text(header):
                        mime_type = f"text/{mime_type}"
            except Exception as e:
                mime_type = None
            if self.current_file.Length() <= 2**28 and (
                mime_type
                and (
                    mime_type.startswith("image")
                    or mime_type.startswith("text")
                    or mime_type == "application/pdf"
                )
            ):
                # Supported mime type for viewer, not too large, load in single read.
                ## Preview
                self.current_file.seek(0)
                chunk = self.current_file.ReadAll()
                self.load_data(chunk, mime_type)

                ## Return to 0 for HexView progressive load
                self.current_file.seek(0)
            else:
                self.text_edit.setPlainText(
                    "File too large to preview or unsupported format."
                )
                self.text_edit.show()

            # Load only hex view, in progressive mode.
            self.hex_viewer.load_next_chunk()

    def show_case_metadata(self):
        case_name = self.volume.resolver.Get(
            self.volume.urn,
            self.volume.urn,
            rdfvalue.URN("http://aff4.org/Schema#caseName"),
        )[0]
        case_description = self.volume.resolver.Get(
            self.volume.urn,
            self.volume.urn,
            rdfvalue.URN("http://aff4.org/Schema#caseDescription"),
        )[0]
        case_examiner = self.volume.resolver.Get(
            self.volume.urn,
            self.volume.urn,
            rdfvalue.URN("http://aff4.org/Schema#examiner"),
        )[0]
        image_start = self.volume.resolver.Get(
            self.volume.urn,
            self.volume.urn,
            rdfvalue.URN("http://aff4.org/Schema#startTime"),
        )[0]
        image_end = self.volume.resolver.Get(
            self.volume.urn,
            self.volume.urn,
            rdfvalue.URN("http://aff4.org/Schema#endTime"),
        )[0]

        case_metadata = "<table>"
        case_metadata += f"<tr><td><b>Case Name:</b></td><td>{case_name}</td></tr>"
        case_metadata += f"<tr><td><b>Examiner:</b></td><td>{case_examiner}</td></tr>"
        case_metadata += f"<tr><td><b>Image Start:</b></td><td>{image_start}</td></tr>"
        case_metadata += f"<tr><td><b>Image End:</b></td><td>{image_end}</td></tr>"
        case_metadata += f"<tr><td><b>Case Description:</b></td><td>{'<br/>'.join(str(case_description).splitlines())}</td></tr>"
        case_metadata += "</table>"

        case_metadata_view = QtWidgets.QTextEdit()
        case_metadata_view.setHtml(case_metadata)
        close_button = QtWidgets.QPushButton("Close")

        case_metadata_layout = QtWidgets.QVBoxLayout()
        case_metadata_layout.addWidget(case_metadata_view)
        case_metadata_layout.addWidget(close_button)

        self.case_metadata_dialog = QtWidgets.QDialog(self)
        close_button.clicked.connect(self.case_metadata_dialog.close)
        self.case_metadata_dialog.setLayout(case_metadata_layout)
        self.case_metadata_dialog.setWindowFlags(
            QtCore.Qt.CustomizeWindowHint | QtCore.Qt.Dialog
        )
        self.case_metadata_dialog.setModal(True)
        self.case_metadata_dialog.setWindowModality(QtCore.Qt.ApplicationModal)
        self.case_metadata_dialog.setMinimumSize(500, 400)
        self.case_metadata_dialog.open()

    def load_metadata(self, urn, folder):
        if urn == "":
            metadata = "No metadata available for selected item. It is likely a virtual tree item."
        else:
            metadata = "<table>"
            metadata += f"<tr><td><b>URN:</b></td><td>{urn}</td></tr>"

            name = self.volume.resolver.Get(
                self.volume.urn, urn, rdfvalue.URN(lexicon.standard11.pathName)
            )[0]
            if folder:
                metadata += f"<tr><td><b>Folder Name:</b></td><td>{name}</td></tr>"
            else:
                metadata += f"<tr><td><b>Filename:</b></td><td>{name}</td></tr>"

            last_access = self.volume.resolver.Get(
                self.volume.urn, urn, rdfvalue.URN(lexicon.standard11.lastAccessed)
            )[0]
            metadata += f"<tr><td><b>Last Access:</b></td><td>{last_access}</td></tr>"
            last_written = self.volume.resolver.Get(
                self.volume.urn, urn, rdfvalue.URN(lexicon.standard11.lastWritten)
            )[0]
            metadata += f"<tr><td><b>Modified:</b></td><td>{last_written}</td></tr>"
            created = self.volume.resolver.Get(
                self.volume.urn, urn, rdfvalue.URN(lexicon.standard11.birthTime)
            )[0]
            metadata += f"<tr><td><b>Created:</b></td><td>{created}</td></tr>"
            record_changed = self.volume.resolver.Get(
                self.volume.urn, urn, rdfvalue.URN(lexicon.standard11.recordChanged)
            )[0]
            metadata += (
                f"<tr><td><b>Record Changed:</b></td><td>{record_changed}</td></tr>"
            )

            if not folder:
                size = self.volume.resolver.Get(
                    self.volume.urn, urn, rdfvalue.URN(lexicon.AFF4_STREAM_SIZE)
                )[0]
                metadata += f"<tr><td><b>Size:</b></td><td>{size} Bytes</td></tr>"
            else:
                metadata += f"<tr><td><b>Size:</b></td><td>N/A</td></tr>"

            if not folder:
                metadata += f"<tr></tr><tr><td><b>Hashes:</b></td></tr>"
                hashes = self.volume.resolver.Get(
                    self.volume.urn, urn, rdfvalue.URN(lexicon.standard.hash)
                )
                for hash in hashes:
                    hash_type = hash.datatype.split("#")[1]
                    metadata += (
                        f"<tr><td><b>{hash_type}</b></td><td>{hash.value}</td></tr>"
                    )

            metadata += "</table>"

        self.metadata_box.clear()
        self.metadata_box.setHtml(metadata)

    @staticmethod
    def parse_exif(exif):
        # Parse EXIF Tags
        # Parse EXIF GPS Tags
        exif_list: [Exif] = []

        exif_gps = exif.get_ifd(ExifTags.IFD.GPSInfo)

        for tag in ExifTags.TAGS:
            tag_name = ExifTags.TAGS[tag]
            try:
                exif_pair = Exif(tag_name, exif[tag])
                if not isinstance(exif_pair.value, bytes):
                    exif_list.append(exif_pair)
            except Exception:
                # Skip missing or problematic tag without making a fuss
                pass

        for tag in ExifTags.GPSTAGS:
            tag_name = ExifTags.GPSTAGS[tag]
            try:
                exif_pair = Exif(tag_name, exif_gps[tag])
                if not isinstance(exif_pair.value, bytes):
                    exif_list.append(exif_pair)
            except Exception:
                # Skip missing or problematic tag without making a fuss
                pass
        return exif_list

    def append_exif(self, data):
        self.metadata_box.moveCursor(QtGui.QTextCursor.End)
        try:
            image = Image.open(io.BytesIO(data))
            exif = image.getexif()
            exif_list: [Exif] = self.parse_exif(exif)
            exif_html = "<hr><table>"
            for exif_pair in exif_list:
                exif_html += f"<tr><td><b>{exif_pair.name}:</b></td><td>{exif_pair.value}</td></tr>"
            exif_html += "</table>"
            self.metadata_box.insertHtml(exif_html)
        except Exception as error:
            print(f"Error when importing image to Pillow image: {error}")

    @staticmethod
    def is_plain_text(sample_data):
        # We test if a file is text by trying to decode a sample of the file. If it works we assume plain text
        # If error, we consider not plain text or unsupported codec and will not try to decode the full file.
        # Successful decoding of sample data might not mean file is plain text and might fail on full decode
        # but it provides a way to rapidly triage.
        try:
            sample_data.decode("utf-8")
            return True
        except Exception:
            return False

    def load_data(self, data, mime_type):

        # Hide all widgets
        self.image_label.clear()
        self.text_edit.clear()
        self.pdf_view.setDocument(None)
        self.image_label.hide()
        self.text_edit.hide()
        self.pdf_view.hide()

        try:
            # Display content based on MIME type

            if mime_type.startswith("image"):
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(data)
                MAX_WIDTH = 600
                MAX_HEIGHT = 400
                # Check if the pixmap dimensions exceed the maximum dimensions
                if pixmap.width() > MAX_WIDTH or pixmap.height() > MAX_HEIGHT:
                    # Scale the pixmap down to fit within the maximum dimensions while maintaining aspect ratio
                    if pixmap.width() / MAX_WIDTH > pixmap.height() / MAX_HEIGHT:
                        # Scale the pixmap to fit the maximum width while maintaining aspect ratio
                        pixmap = pixmap.scaledToWidth(MAX_WIDTH)
                    else:
                        # Scale the pixmap to fit the maximum height while maintaining aspect ratio
                        pixmap = pixmap.scaledToHeight(MAX_HEIGHT)

                self.image_label.setPixmap(pixmap)
                self.image_label.show()
                self.append_exif(data)
            elif mime_type.startswith("text"):
                text = data.decode("utf-8", "ignore")
                self.text_edit.setPlainText(text)
                self.text_edit.show()
            elif mime_type == "application/pdf":
                buffer = QtCore.QBuffer()
                buffer.setData(QtCore.QByteArray(data))
                buffer.open(QtCore.QIODevice.ReadOnly)

                self.pdf_doc = QtPdf.QPdfDocument()
                self.pdf_doc.load(buffer)
                self.pdf_view.setDocument(self.pdf_doc)
                self.pdf_view.show()

        except Exception as e:
            # Hide all widgets
            self.image_label.clear()
            self.text_edit.clear()
            self.image_label.hide()

            self.text_edit.setPlainText(
                f"Error loading file preview:\n{traceback.format_exc()}"
            )
            self.text_edit.show()
