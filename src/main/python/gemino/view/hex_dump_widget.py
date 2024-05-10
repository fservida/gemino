from PySide6 import QtWidgets, QtCore, QtGui


class HexDumpWidget(QtWidgets.QPlainTextEdit):

    BYTES_PER_LINE = 16
    BOTTOM_MARGIN = 1
    FONT_SIZE = 12
    CHUNK_SIZE = 4096  # Adjust chunk size as needed

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
        widget_height = self.height()
        # font_size = self.hex_viewer.fontMetrics().height()
        lines_per_page = int(round(widget_height / self.FONT_SIZE))
        total_lines = (
            self.current_file.Length() / self.BYTES_PER_LINE if self.current_file else 0
        )
        scrollbar_max_lines = total_lines - lines_per_page + self.BOTTOM_MARGIN
        return scrollbar_max_lines, lines_per_page

    def load_next_chunk(self):
        file_size = self.current_file.Length()
        if self.loaded_data < file_size:
            self.current_file.seek(self.loaded_data)
            chunk = self.current_file.Read(self.CHUNK_SIZE)
            hex_dump = self.format_hex_dump(chunk, self.loaded_data, self.BYTES_PER_LINE)
            self.moveCursor(QtGui.QTextCursor.End) # Move cursor at end before inserting new data
            self.insertPlainText(hex_dump + "\n")
            self.loaded_data += len(chunk)
            self.adjust_scrollbar()

    def adjust_scrollbar(self):
        scrollbar = self.verticalScrollBar()
        if self.current_file and self.loaded_data < self.current_file.Length():
            # Use custom scrollbar display only if not everything is loaded.
            # This should avoid issues with alignment of last lines.
            scrollbar = self.verticalScrollBar()
            scrollbar_range, scrollbar_step = self.get_scrollbar_settings()
            scrollbar.setRange(0, scrollbar_range)
            scrollbar.setPageStep(scrollbar_step)
        else:
            pass

    def preload_on_scrollbar_change(self):
        scrollbar = self.verticalScrollBar()
        scrollbar_range, scrollbar_step = self.get_scrollbar_settings()
        # print(
        #     scrollbar.value(),
        #     scrollbar.maximum(),
        #     scrollbar_range,
        #     self.loaded_data,
        #     self.height(),
        # )
        while (
            scrollbar.value()
            and (
                (scrollbar.value() + scrollbar_step) * self.BYTES_PER_LINE
                >= self.loaded_data
            )
            and self.loaded_data < self.current_file.Length()
        ):
            self.load_next_chunk()

    @staticmethod
    def format_hex_dump(data, offset, bytes_per_line):
        formatted_text = ""
        for i in range(0, len(data), bytes_per_line):
            chunk = data[i : i + bytes_per_line]
            chunk_len = len(chunk)
            hex_line = f"{offset + i:010X} | "
            ascii_line = ""
            for b in chunk:
                hex_line += f" {b:02X}"
                ascii_line += chr(b) if 32 <= b < 127 else "."
            if chunk_len < bytes_per_line:
                for _ in range(0, bytes_per_line-chunk_len):
                    hex_line += f"   "  # 3 empty spaces: a spacer, and 2 to match missing 00
            formatted_text += f"{hex_line}   {ascii_line}\n"
        return formatted_text.rstrip("\n")

