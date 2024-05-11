from dataclasses import dataclass


@dataclass
class ProgressData:
    status: int
    payload: dict