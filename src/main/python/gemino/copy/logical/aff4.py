# Utils specific to AFF4 container creation, and placeholder for subclass for AFF4 logical imaging.

from pyaff4 import utils, rdfvalue, escaping, lexicon, zip, container
from pyaff4.aff4 import ProgressContext
from past.utils import old_div
from dataclasses import dataclass
from urllib.parse import unquote


from ..utils import ProgressData


class ProgressContextListener(ProgressContext):

    copy_progress = None
    destinations = None
    processed_files = None
    current_file = None
    status = ""
    main_status = 0

    def __init__(self, *args, **kwargs):
        super(ProgressContext, self).__init__(*args, **kwargs)

    def Report(self, readptr):
        readptr = readptr + self.start
        now = self.now()
        if now > self.last_time + old_div(1000000, 4):
            self.last_time = now
            self.last_offset = readptr
            self.copy_progress.emit(
                ProgressData(
                    status=self.main_status,
                    payload={
                        dst: {
                            "status": self.status,
                            "processed_bytes": readptr,
                            "processed_files": self.processed_files,
                            "current_file": self.current_file,
                        }
                        for dst in self.destinations
                    },
                )
            )


class LinearVerificationListener(object):
    def __init__(self, volume):
        self.volume = volume
        self.failed = {}

    def onValidHash(self, typ, hash, imageStreamURI):
        pass

    def onInvalidHash(self, typ, hasha, hashb, streamURI):
        file = streamURI
        data = (typ, hasha, hashb, trimVolume(self.volume, streamURI))
        print("\t\t%s Hash failure stored = %s calculated = %s, %s)" % data)
        if file not in self.failed:
            self.failed[file] = [data]
        else:
            self.failed[file].append(data)


def trimVolume(volume, image):
    """
    Shamelessly taken from aff4.py from aff4/pyaff4
    :param volume: volume.urn
    :param image: image.urn
    :return: only file path, without aff://...// part
    """
    volstring = utils.SmartUnicode(volume)
    imagestring = utils.SmartUnicode(image)
    if imagestring.startswith(volstring):
        imagestring = imagestring[len(volstring) :]
    if imagestring.startswith("//"):
        imagestring = imagestring[2:]
    return imagestring


def get_container_summary(src):
    """
    :return: file number, total size (bytes)
    """
    filecount = 0
    total_size = 0

    with container.Container.openURNtoContainer(
        rdfvalue.URN.FromFileName(src)
    ) as volume:

        for image in volume.images():
            # Each image is a file in the container.
            # Update Byte Progress
            filecount += 1
            filesize = int(
                image.resolver.store.get(image.urn).get(lexicon.AFF4_STREAM_SIZE)
            )
            total_size += filesize

    return filecount, total_size


@dataclass
class AFF4Item:
    name: str
    size: dict
    modify: str
    create: str
    urn: str
    path: str
    folder: bool = False


def get_metadata(src):
    """
    :return: file number, total size (bytes)
    """
    items = {}

    volume = container.Container.openURNtoContainer(rdfvalue.URN.FromFileName(src))

    for folder in volume.resolver.QueryPredicateObject(
        volume.urn, lexicon.AFF4_TYPE, lexicon.standard11.FolderImage
    ):
        path = unquote(folder.Parse().path[1:])

        items[path] = AFF4Item(
            name=None,
            size=None,
            modify=str(
                volume.resolver.store.get(folder).get(lexicon.standard11.lastWritten)
            ),
            create=str(
                volume.resolver.store.get(folder).get(lexicon.standard11.birthTime)
            ),
            urn=folder,
            path=path,
            folder=True,
        )

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
                volume.resolver.store.get(image.urn).get(lexicon.standard11.lastWritten)
            ),
            create=str(
                volume.resolver.store.get(image.urn).get(lexicon.standard11.birthTime)
            ),
            urn=image.urn,
            path=path,
        )

    return volume, dict(sorted(items.items()))
