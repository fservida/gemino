from dataclasses import dataclass


@dataclass
class AFF4Item:
    name: str
    size: int
    modify: str
    create: str
    urn: str
    path: str
    folder: bool = False
