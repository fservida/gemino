from threading import Thread


class CopyBuffer(Thread):
    def __init__(self, buffer, file_handler):
        super().__init__()
        self.buffer = buffer
        self.file_handler = file_handler

    def run(self):
        # print("Thread {} - Starting copy to {}".format(current_thread(), self.file_handler.name))
        self.file_handler.write(self.buffer)
        # print("Thread {} - Finished copy to {}".format(current_thread(), self.file_handler.name))
