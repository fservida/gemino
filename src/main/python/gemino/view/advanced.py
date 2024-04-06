import base64
from typing import Union
import puremagic

from PySide6 import QtWidgets, QtCore, QtGui
from pathlib import Path

from PySide6.QtWebEngineWidgets import QWebEngineView
from pyaff4.container import (
    PhysicalImageContainer,
    WritableHashBasedImageContainer,
    LogicalImageContainer,
    PreStdLogicalImageContainer,
    EncryptedImageContainer,
)

from .viewer_libraries import PDF_JS_MIN, PDF_JS_MIN_WORKER, JSZIP_JS_MIN, DOCX_JS_MIN
from ..copy.logical.aff4 import AFF4Item


class AdvancedWidget(QtWidgets.QWidget):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        aff4_volume: Union[
            PhysicalImageContainer,
            WritableHashBasedImageContainer,
            LogicalImageContainer,
            PreStdLogicalImageContainer,
            EncryptedImageContainer,
        ],
        aff4_items: dict[str, AFF4Item],
    ):
        super().__init__(parent=parent)

        self.volume = aff4_volume

        # Instantiate Widgets
        ## Top
        self.tree_view = QtWidgets.QTreeWidget()

        ## Separation
        self.dst_hbar = QtWidgets.QFrame()
        self.dst_hbar.setFrameShape(QtWidgets.QFrame.HLine)

        ## Bottom
        self.export_button = QtWidgets.QPushButton("View")
        self.export_button.clicked.connect(self.view_details)

        ## Hex Viewer
        self.hex_viewer = QtWidgets.QPlainTextEdit()
        self.hex_viewer.setReadOnly(True)
        self.hex_viewer.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.hex_viewer.verticalScrollBar().valueChanged.connect(
            self.on_scrollbar_value_changed
        )
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.hex_viewer.setFont(font)
        self.loaded_data = 0

        ## Image label
        self.image_label = QtWidgets.QLabel()

        ## Text edit
        self.text_edit = QtWidgets.QTextEdit()
        self.text_edit.setReadOnly(True)  # Set readonly

        ## Web engine view for PDF and office documents
        self.web_view = QWebEngineView()

        # Initially hide all widgets
        self.image_label.hide()
        self.text_edit.hide()
        self.web_view.hide()

        ## Layout Management
        self.window_layout = QtWidgets.QVBoxLayout()

        self.window_layout.addWidget(self.tree_view)
        self.window_layout.addWidget(self.dst_hbar)
        self.window_layout.addWidget(self.export_button)

        self.viewer_layout = QtWidgets.QHBoxLayout()
        self.viewer_layout.addWidget(self.hex_viewer)
        self.viewer_layout.addWidget(self.image_label)
        self.viewer_layout.addWidget(self.text_edit)
        self.viewer_layout.addWidget(self.web_view)

        self.window_layout.addLayout(self.viewer_layout)
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

    def view_details(self):
        urn = self.tree_view.selectedItems()[0].data(5, 0)
        folder = self.tree_view.selectedItems()[0].data(4, 0) == "True"
        self.loaded_data = 0

        # Clear interface
        self.hex_viewer.clear()
        self.image_label.clear()
        self.text_edit.clear()
        self.web_view.setHtml("")
        self.image_label.hide()
        self.text_edit.hide()
        self.web_view.hide()
        if not folder:
            self.current_file = self.volume.resolver.AFF4FactoryOpen(urn)
            header = self.current_file.Read(4096)
            try:
                mime_type = puremagic.magic_string(header)[0].mime_type
            except Exception as e:
                mime_type = None
            if self.current_file.length <= 2**28 and (
                mime_type
                and (
                    mime_type.startswith("image")
                    or mime_type.startswith("text")
                    or mime_type == "application/pdf"
                    or mime_type
                    == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            ):
                # Supported mime type for viewer, not too large, load in single read.
                ## Hex View
                self.current_file.seek(0)
                chunk = self.current_file.ReadAll()
                hex_dump = self.format_hex_dump(chunk, self.loaded_data)
                self.hex_viewer.insertPlainText(hex_dump)
                self.loaded_data += len(chunk)
                ## Preview
                self.load_data(chunk, mime_type)
            else:
                self.text_edit.setPlainText(
                    "File too large to preview or unsupported format."
                )
                self.text_edit.show()

                # Load only hex view, in progressive mode.
                self.load_next_chunk()

                scrollbar = self.hex_viewer.verticalScrollBar()
                scrollbar_range, scrollbar_step = self.get_scrollbar_settings()
                scrollbar.setRange(0, scrollbar_range)
                scrollbar.setPageStep(scrollbar_step)

    def load_next_chunk(self):
        chunk_size = 1024  # Adjust chunk size as needed
        file_size = self.current_file.length
        if self.loaded_data < file_size:
            self.current_file.seek(self.loaded_data)
            chunk = self.current_file.Read(chunk_size)
            hex_dump = self.format_hex_dump(chunk, self.loaded_data)
            self.hex_viewer.insertPlainText(hex_dump + "\n")
            scrollbar = self.hex_viewer.verticalScrollBar()
            scrollbar_range, scrollbar_step = self.get_scrollbar_settings()
            scrollbar.setRange(0, scrollbar_range)
            scrollbar.setPageStep(scrollbar_step)
            self.loaded_data += len(chunk)

    def format_hex_dump(self, data, offset):
        formatted_text = ""
        for i in range(0, len(data), 16):
            chunk = data[i : i + 16]
            hex_line = f"{offset + i:010X} | "
            ascii_line = ""
            for b in chunk:
                hex_line += f" {b:02X}"
                ascii_line += chr(b) if 32 <= b < 127 else "."
            formatted_text += f"{hex_line}   {ascii_line}\n"
        return formatted_text.lstrip("\n")

    def on_scrollbar_value_changed(self):
        scrollbar = self.hex_viewer.verticalScrollBar()
        print(
            scrollbar.value(),
            scrollbar.maximum(),
            self.loaded_data,
            self.hex_viewer.height(),
        )
        if scrollbar.value() and scrollbar.maximum():
            if scrollbar.value() + self.hex_viewer.height() / scrollbar.maximum() >= (
                self.loaded_data / self.current_file.length
            ):
                self.load_next_chunk()

    def get_scrollbar_settings(self):
        widget_height = self.hex_viewer.height()
        # font_size = self.hex_viewer.fontMetrics().height()
        font_size = 12
        lines_per_page = widget_height / font_size
        bytes_per_line = 16
        total_height = self.current_file.length / bytes_per_line * font_size
        return total_height, widget_height

    def load_data(self, data, mime_type):

        # Hide all widgets
        self.image_label.clear()
        self.text_edit.clear()
        self.web_view.setHtml("")
        self.image_label.hide()
        self.text_edit.hide()
        self.web_view.hide()

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
                # image_data = base64.b64encode(data).decode('utf-8')
                # html = (
                #         """
                #             <!DOCTYPE html>
                #             <html>
                #             <head>
                #                 <title>Image Viewer</title>
                #                 <meta charset="UTF-8">
                #                 <style>
                #                 </style>
                #             </head>
                #             <body>
                #                 <img style="width: 100%%" src='data:%s;base64,%s'>
                #             </body>
                #             </html>
                #         """ % (mime_type, image_data))
                # self.web_view.setHtml(html)
                # with open('test.html', 'w') as file:
                #     file.write(html)
                # self.web_view.show()
            elif mime_type.startswith("text"):
                text = data.decode("utf-8")
                self.text_edit.setPlainText(text)
                self.text_edit.show()
            elif mime_type == "application/pdf":
                pdf_js_data = PDF_JS_MIN
                pdf_worker_data = PDF_JS_MIN_WORKER
                pdf_data_base64 = base64.b64encode(data).decode("utf-8")
                html = """
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <title>Gemino PDF Viewer - Based on PDF.js</title>
                            <meta charset="UTF-8">
                        </head>
                        <body>

                        </body>
                        </html>
                    """
                self.page_content = """
                        <script type="text/javascript" src="data:text/javascript;base64,%s" ></script>
                        <style>
                                #pdf-viewer {
                                    width: 100%%;
                                    height: 100%%;
                                }
                                .pdf-page {
                                    box-shadow: 0 4px 8px 0 rgba(0, 0, 0, 0.2), 0 6px 20px 0 rgba(0, 0, 0, 0.19);
                                    margin: 5px;
                                }
                        </style>
                        <div id="pdf-viewer"></div>
                        <script>
                            const pdfData = "%s";
                            const pdfUrl = "data:application/pdf;base64," + pdfData;
                            pdfjsLib.GlobalWorkerOptions.workerSrc = 'data:application/javascript;base64,%s';
                            pdfjsLib.getDocument(pdfUrl).promise.then(function(pdf) {
                                const viewerContainer = document.getElementById('pdf-viewer');
                                for (let i = 1; i <= pdf.numPages; i++) {
                                    const page = document.createElement('div');
                                    viewerContainer.appendChild(page);
                                    pdf.getPage(i).then(function(pdfPage) {
                                        const viewport = pdfPage.getViewport({ scale: 1 });
                                        const canvas = document.createElement('canvas');
                                        const context = canvas.getContext('2d');
                                        canvas.height = viewport.height;
                                        canvas.width = viewport.width;
                                        canvas.classList.add('pdf-page');
                                        page.appendChild(canvas);
                                        pdfPage.render({
                                            canvasContext: context,
                                            viewport: viewport
                                        });
                                    });
                                }
                            });
                        </script>
                    """ % (
                    pdf_js_data,
                    pdf_data_base64,
                    pdf_worker_data,
                )
                self.web_view.loadFinished.connect(self.load_view)

                web_page = self.web_view.page()
                web_page.setHtml(html)

                self.web_view.show()

            elif (
                mime_type
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ):
                jszip_js_min = JSZIP_JS_MIN
                docx_js_min = DOCX_JS_MIN
                docx_data_base64 = base64.b64encode(data).decode("utf-8")
                html = """
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <title>Gemino DOCX Viewer - Based on docx.js</title>
                                <meta charset="UTF-8">

                            </head>
                            <body>
                                
                            </body>
                            </html>
                        """
                self.page_content = """
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <title>Gemino DOCX Viewer - Based on docx.js</title>
                                <meta charset="UTF-8">
                                
                            </head>
                            <body>
                                <div id="container"></div>
                                <script type="text/javascript" src="data:text/javascript;base64,%s"></script>
                                <script type="text/javascript" src="data:text/javascript;base64,%s"></script>
                                <script>
                                    const base64String = '%s';
                                    
                                    const b64toBlob = (b64Data, contentType='', sliceSize=512) => {
                                      const byteCharacters = atob(b64Data);
                                      const byteArrays = [];

                                      for (let offset = 0; offset < byteCharacters.length; offset += sliceSize) {
                                        const slice = byteCharacters.slice(offset, offset + sliceSize);

                                        const byteNumbers = new Array(slice.length);
                                        for (let i = 0; i < slice.length; i++) {
                                          byteNumbers[i] = slice.charCodeAt(i);
                                        }

                                        const byteArray = new Uint8Array(byteNumbers);
                                        byteArrays.push(byteArray);
                                      }

                                      const blob = new Blob(byteArrays, {type: contentType});
                                      return blob;
                                    }
                                </script>
                                <script>
                                    async function parse_doc() {
                                        const blob = b64toBlob(base64String, 'application/octet-stream');
                                        docx.renderAsync(blob, document.getElementById("container"))
                                            .then(x => console.log("docx: finished"));
                                    }
                                    parse_doc();
                                </script>
                            </body>
                            </html>
                        """ % (
                    jszip_js_min,
                    docx_js_min,
                    docx_data_base64,
                )
                self.web_view.loadFinished.connect(self.load_view)

                web_page = self.web_view.page()
                web_page.setHtml(html)

                self.web_view.show()

        except Exception as e:
            # Hide all widgets
            self.image_label.clear()
            self.text_edit.clear()
            self.web_view.setHtml("")
            self.image_label.hide()
            self.web_view.hide()

            self.text_edit.setPlainText("Error loading file preview.")
            self.text_edit.show()

    def load_view(self, finished=None):
        web_page = self.web_view.page()
        web_page.runJavaScript(f"document.write(`{self.page_content}`);")
        self.page_content = ""
