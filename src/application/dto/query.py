from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class PlayerStatsSummary:
    display_name: str
    total_matches: int
    wins: int
    losses: int
    win_rate: float
    average_points_won: float
    average_winners: float
    average_serve_points_won: float
    average_errors: float
    average_double_faults: float
    average_net_play_rate: float | None
    average_max_serve_speed_kmh: float | None = None


@dataclass(slots=True)
class RecentMatchItem:
    match_code: str
    confirmed_at: datetime | None
    is_winner: bool
    opponent_name: str
    points_won: int | None
    opponent_points_won: int | None
    duration_seconds: int | None


@dataclass(slots=True)
class DoublesRecentMatchItem:
    match_code: str
    confirmed_at: datetime | None
    is_winner: bool
    teammate_name: str
    opponent_names: list[str]
    team_points_won: int | None
    opponent_team_points_won: int | None
    player_points_won: int | None
    duration_seconds: int | None
