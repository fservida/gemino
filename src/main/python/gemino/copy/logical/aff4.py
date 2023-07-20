# Utils specific to AFF4 container creation, and placeholder for subclass for AFF4 logical imaging.

from pyaff4 import utils, rdfvalue, escaping, lexicon, zip


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
        imagestring = imagestring[len(volstring):]
    if imagestring.startswith("//"):
        imagestring = imagestring[2:]
    return imagestring