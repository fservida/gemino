from PySide6.QtCore import QThread, Signal
from pyaff4 import utils, rdfvalue, escaping, lexicon, zip, container
from urllib.parse import unquote

from ..common.utils import ProgressData
from ..common.threads import TaskThread
from .common import AFF4Item
from .utils import iterate_folder


class OpenContainerThread(TaskThread):

    def __init__(self, src):
        super().__init__()
        self.__src = src

    def task(self):
        """
        :return: volume, items
        """
        items = {}

        volume = container.Container.openURNtoContainer(
            rdfvalue.URN.FromFileName(self.__src)
        )

        iterate_folder(items, volume, lexicon.standard11.FolderImage)
        # This is to be compliant with unicode.aff4 in reference images,
        # although it looks like an issue with reference image or base library.
        iterate_folder(items, volume, lexicon.standard11.base + "FolderImage")

        processed_items = 0

        for image in volume.images():
            # Each image is a file in the container.

            filesize = int(
                volume.resolver.store.get(image.urn).get(lexicon.AFF4_STREAM_SIZE)
            )
            path = unquote(image.urn.Parse().path[1:])
            items[path] = AFF4Item(
                name=None,
                size=filesize,
                modify=str(
                    volume.resolver.store.get(image.urn).get(
                        lexicon.standard11.lastWritten
                    )
                ),
                create=str(
                    volume.resolver.store.get(image.urn).get(
                        lexicon.standard11.birthTime
                    )
                ),
                urn=image.urn,
                path=path,
            )
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
                    "aff4_volume": volume,
                    "aff4_items": dict(sorted(items.items())),
                    "src_container_path": self.__src,
                },
            )
        )
