# Utils specific to AFF4 container creation, and placeholder for subclass for AFF4 logical imaging.

from pyaff4 import utils, rdfvalue, escaping, lexicon, zip
from pyaff4.version import Version
from pyaff4.container import WritableLogicalImageContainer
import uuid


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


def writeLogicalStream(volume, filename, readstream, length):
    image_urn = None
    if volume.isAFF4Collision(filename):
        image_urn = rdfvalue.URN("aff4://%s" % uuid.uuid4())
    else:
        image_urn = volume.urn.Append(escaping.arnPathFragment_from_path(filename), quote=False)

    volume.writeZipStream(image_urn, filename, readstream)
    volume.resolver.Add(volume.urn, image_urn, rdfvalue.URN(lexicon.AFF4_TYPE),
                        rdfvalue.URN(lexicon.AFF4_ZIP_SEGMENT_IMAGE_TYPE))

    volume.resolver.Add(volume.urn, image_urn, rdfvalue.URN(lexicon.AFF4_TYPE), rdfvalue.URN(lexicon.standard11.FileImage))
    volume.resolver.Add(volume.urn, image_urn, rdfvalue.URN(lexicon.AFF4_TYPE), rdfvalue.URN(lexicon.standard.Image))
    volume.resolver.Add(volume.urn, image_urn, rdfvalue.URN(lexicon.standard11.pathName), rdfvalue.XSDString(filename))
    return image_urn

def createURN(resolver, container_urn, encryption=False):
    """Public method to create a new writable locical AFF4 container."""

    resolver.Set(lexicon.transient_graph, container_urn, lexicon.AFF4_STREAM_WRITE_MODE, rdfvalue.XSDString("truncate"))

    version = Version(1, 1, "pyaff4")
    with zip.ZipFile.NewZipFile(resolver, version, container_urn) as zip_file:
        volume_urn = zip_file.urn
        with resolver.AFF4FactoryOpen(zip_file.backing_store_urn) as backing_store:
            return WritableLogicalImageContainer(backing_store, zip_file, version, volume_urn, resolver, lexicon.standard)

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
        imagestring = imagestring[len(volstring):]
    if imagestring.startswith("//"):
        imagestring = imagestring[2:]
    return imagestring