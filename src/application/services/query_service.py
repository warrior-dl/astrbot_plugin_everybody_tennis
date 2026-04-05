from sqlalchemy import select

from ..dto.query import PlayerStatsSummary, RecentMatchItem
from ...infrastructure.persistence.db import DatabaseManager
from ...infrastructure.persistence.models import Group, Match, MatchPlayerStat
from ...shared.text import normalize_name


class QueryError(Exception):
    pass


class QueryService:
    def __init__(self, db: DatabaseManager):
        self._db = db

    async def get_player_stats(
        self,
        *,
        platform: str,
        external_group_id: str,
        game_nickname: str,
    ) -> PlayerStatsSummary:
        normalized_name = normalize_name(game_nickname)
        if not normalized_name:
            raise QueryError("请在命令后指定游戏内昵称。")

        async with self._db.session() as session:
            group = await self._get_group(
                platform=platform,
                external_group_id=external_group_id,
                session=session,
            )
            if group is None:
                raise QueryError("当前群还没有任何比赛记录。")

            stmt = (
                select(MatchPlayerStat, Match)
                .join(Match, MatchPlayerStat.match_id == Match.id)
                .where(Match.group_id == group.id)
                .where(MatchPlayerStat.normalized_player_name == normalized_name)
                .where(Match.status == "confirmed")
                .order_by(Match.confirmed_at.desc(), Match.id.desc())
            )
            rows = (await session.execute(stmt)).all()
            if not rows:
                raise QueryError(f"未找到昵称 `{game_nickname.strip()}` 的已确认比赛记录。")

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
                display_name=rows[0][0].raw_player_name,
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
        game_nickname: str,
        limit: int = 5,
    ) -> list[RecentMatchItem]:
        normalized_name = normalize_name(game_nickname)
        if not normalized_name:
            raise QueryError("请在命令后指定游戏内昵称。")

        async with self._db.session() as session:
            group = await self._get_group(
                platform=platform,
                external_group_id=external_group_id,
                session=session,
            )
            if group is None:
                raise QueryError("当前群还没有任何比赛记录。")

            stmt = (
                select(MatchPlayerStat, Match)
                .join(Match, MatchPlayerStat.match_id == Match.id)
                .where(Match.group_id == group.id)
                .where(MatchPlayerStat.normalized_player_name == normalized_name)
                .where(Match.status == "confirmed")
                .order_by(Match.confirmed_at.desc(), Match.id.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
            if not rows:
                raise QueryError(f"未找到昵称 `{game_nickname.strip()}` 的已确认比赛记录。")

            results: list[RecentMatchItem] = []
            for stat, match in rows:
                opponent_stmt = (
                    select(MatchPlayerStat)
                    .where(MatchPlayerStat.match_id == match.id)
                    .where(MatchPlayerStat.side != stat.side)
                    .limit(1)
                )
                opponent_row = (await session.execute(opponent_stmt)).first()
                opponent_stat = opponent_row[0] if opponent_row else None
                opponent_name = opponent_stat.raw_player_name if opponent_stat is not None else "未知对手"
                results.append(
                    RecentMatchItem(
                        match_code=match.match_code,
                        confirmed_at=match.confirmed_at,
                        is_winner=stat.is_winner,
                        opponent_name=opponent_name,
                        points_won=stat.points_won,
                        opponent_points_won=opponent_stat.points_won if opponent_stat is not None else None,
                        duration_seconds=match.duration_seconds,
                    )
                )
            return results

    async def _get_group(
        self,
        *,
        platform: str,
        external_group_id: str,
        session,
    ) -> Group | None:
        stmt = (
            select(Group)
            .where(Group.platform == platform)
            .where(Group.external_group_id == external_group_id)
        )
        return await session.scalar(stmt)
