from pyaff4 import rdfvalue, lexicon, container

from ..common.utils import ProgressData
from ..common.threads import TaskThread


class GetSummaryThread(TaskThread):

    def __init__(self, src):
        super().__init__()
        self.__src = src

    def task(self):
        """
        :return: file number, total size (bytes)
        """
        filecount = 0
        total_size = 0

        with container.Container.openURNtoContainer(
            rdfvalue.URN.FromFileName(self.__src)
        ) as volume:
            processed_items = 0
            for image in volume.images():
                # Each image is a file in the container.
                # Update Byte Progress
                filecount += 1
                filesize = int(
                    image.resolver.store.get(image.urn).get(lexicon.AFF4_STREAM_SIZE)
                )
                total_size += filesize
                processed_items += 1
                self.task_progress.emit(
                    ProgressData(
                        1,
                        {
                            "current_item": str(image.urn),
                            "processed_items": processed_items,
                        },
                    )
                )

        self.task_progress.emit(
            ProgressData(
                0,
                {
                    "total_files": filecount,
                    "total_size": total_size,
                    "src_container_path": self.__src,
                },
            )
        )
