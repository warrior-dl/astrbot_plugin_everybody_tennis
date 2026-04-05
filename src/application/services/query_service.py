from sqlalchemy import select

from src.application.dto.query import PlayerStatsSummary, RecentMatchItem
from src.application.services.identity_service import IdentityService
from src.infrastructure.persistence.db import DatabaseManager
from src.infrastructure.persistence.models import Match, MatchPlayerStat, Player


class QueryError(Exception):
    pass


class QueryService:
    def __init__(self, db: DatabaseManager, identity_service: IdentityService):
        self._db = db
        self._identity_service = identity_service

    async def get_player_stats(
        self,
        *,
        platform: str,
        external_group_id: str,
        platform_user_id: str,
    ) -> PlayerStatsSummary:
        async with self._db.session() as session:
            player = await self._identity_service.get_player_by_platform_user(
                platform=platform,
                external_group_id=external_group_id,
                platform_user_id=platform_user_id,
                session=session,
            )
            if player is None:
                raise QueryError("你还没有绑定游戏昵称，请先使用 `/网球 绑定 <游戏昵称>`。")

            stmt = (
                select(MatchPlayerStat, Match)
                .join(Match, MatchPlayerStat.match_id == Match.id)
                .where(MatchPlayerStat.player_id == player.id)
                .where(Match.status == "confirmed")
                .order_by(Match.confirmed_at.desc(), Match.id.desc())
            )
            rows = (await session.execute(stmt)).all()
            if not rows:
                raise QueryError("你还没有已确认的比赛记录。")

            total_matches = len(rows)
            wins = sum(1 for stat, _match in rows if stat.is_winner)
            total_points = sum(stat.points_won or 0 for stat, _match in rows)
            total_winners = sum(stat.winners or 0 for stat, _match in rows)
            total_serve_points = sum(stat.serve_points_won or 0 for stat, _match in rows)
            total_errors = sum(stat.errors or 0 for stat, _match in rows)
            total_double_faults = sum(stat.double_faults or 0 for stat, _match in rows)
            net_rates = [
                stat.net_play_rate for stat, _match in rows if stat.net_play_rate is not None
            ]

            return PlayerStatsSummary(
                display_name=player.display_name,
                total_matches=total_matches,
                wins=wins,
                losses=total_matches - wins,
                win_rate=wins / total_matches if total_matches else 0.0,
                total_points_won=total_points,
                total_winners=total_winners,
                total_serve_points_won=total_serve_points,
                total_errors=total_errors,
                total_double_faults=total_double_faults,
                average_net_play_rate=(
                    sum(net_rates) / len(net_rates) if net_rates else None
                ),
            )

    async def get_recent_matches(
        self,
        *,
        platform: str,
        external_group_id: str,
        platform_user_id: str,
        limit: int = 5,
    ) -> list[RecentMatchItem]:
        async with self._db.session() as session:
            player = await self._identity_service.get_player_by_platform_user(
                platform=platform,
                external_group_id=external_group_id,
                platform_user_id=platform_user_id,
                session=session,
            )
            if player is None:
                raise QueryError("你还没有绑定游戏昵称，请先使用 `/网球 绑定 <游戏昵称>`。")

            stmt = (
                select(MatchPlayerStat, Match)
                .join(Match, MatchPlayerStat.match_id == Match.id)
                .where(MatchPlayerStat.player_id == player.id)
                .where(Match.status == "confirmed")
                .order_by(Match.confirmed_at.desc(), Match.id.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
            if not rows:
                raise QueryError("你还没有已确认的比赛记录。")

            results: list[RecentMatchItem] = []
            for stat, match in rows:
                opponent_stmt = (
                    select(MatchPlayerStat, Player)
                    .outerjoin(Player, MatchPlayerStat.player_id == Player.id)
                    .where(MatchPlayerStat.match_id == match.id)
                    .where(MatchPlayerStat.side != stat.side)
                    .limit(1)
                )
                opponent_row = (await session.execute(opponent_stmt)).first()
                opponent_stat, opponent_player = opponent_row if opponent_row else (None, None)
                opponent_name = (
                    opponent_player.display_name
                    if opponent_player is not None
                    else (opponent_stat.raw_player_name if opponent_stat is not None else "未知对手")
                )
                results.append(
                    RecentMatchItem(
                        match_code=match.match_code,
                        confirmed_at=match.confirmed_at,
                        is_winner=stat.is_winner,
                        opponent_name=opponent_name,
                        points_won=stat.points_won,
                        opponent_points_won=(
                            opponent_stat.points_won if opponent_stat is not None else None
                        ),
                        duration_seconds=match.duration_seconds,
                    )
                )
            return results
