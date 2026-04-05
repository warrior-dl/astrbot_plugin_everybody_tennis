from dataclasses import dataclass


@dataclass(slots=True)
class RankingEntry:
    rank: int
    display_name: str
    matches: int
    wins: int
    value: float
    metric_key: str

