from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class PlayerStatsSummary:
    display_name: str
    total_matches: int
    wins: int
    losses: int
    win_rate: float
    total_points_won: int
    total_winners: int
    total_serve_points_won: int
    total_errors: int
    total_double_faults: int
    average_net_play_rate: float | None


@dataclass(slots=True)
class RecentMatchItem:
    match_code: str
    confirmed_at: datetime | None
    is_winner: bool
    opponent_name: str
    points_won: int | None
    opponent_points_won: int | None
    duration_seconds: int | None

