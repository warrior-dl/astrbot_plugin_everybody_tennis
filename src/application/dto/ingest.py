from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class IngestPlayerPreview:
    side: int
    player_slot: int
    raw_name: str
    points_won: int | None
    winners: int | None
    serve_points_won: int | None
    errors: int | None
    double_faults: int | None
    net_play_rate: float | None
    max_serve_speed_kmh: int | None


@dataclass(slots=True)
class IngestPreview:
    match_code: str
    match_type: str
    status: str
    players: list[IngestPlayerPreview]
    set_count: int | None
    game_count: int | None
    duration_seconds: int | None
    max_rally_count: int | None
    missing_fields: list[str]
    duplicate_hint: bool
    expires_at: datetime | None
    auto_confirmed: bool
