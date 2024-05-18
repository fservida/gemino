from pyaff4 import utils, rdfvalue, escaping, lexicon, zip, container
from urllib.parse import unquote
from zipfile import ZipFile

from .common import AFF4Item


def iterate_folder(items, volume, rdf_lexicon):
    for folder in volume.resolver.QueryPredicateObject(
        volume.urn, lexicon.AFF4_TYPE, rdf_lexicon
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


def number_of_items(src: str) -> int:
    """
    Returns number of items contained in a ZIP file,
    used as fast method to calculate how many items we need to iterate over
    for displaying a more or less accurate loading bar
    :param src: AFF4-L container
    :return: number of files
    """
    with ZipFile(src) as myzip:
        items = myzip.infolist()

    return len(items)
