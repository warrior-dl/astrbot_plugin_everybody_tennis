from ..dto.query import DoublesRecentMatchItem, PlayerStatsSummary, RecentMatchItem
from ...infrastructure.persistence.db import DatabaseManager
from ...infrastructure.persistence.models import Match, MatchPlayerStat
from ...shared.match_types import MATCH_TYPE_DOUBLES, MATCH_TYPE_SINGLES
from ...shared.text import normalize_name
from ._scope import GroupScopedLookup
from sqlalchemy import select


class QueryError(Exception):
    pass


class QueryService(GroupScopedLookup):
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
                .where(Match.match_type == MATCH_TYPE_SINGLES)
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
                average_points_won=total_points / total_matches if total_matches else 0.0,
                average_winners=total_winners / total_matches if total_matches else 0.0,
                average_serve_points_won=(
                    total_serve_points / total_matches if total_matches else 0.0
                ),
                average_errors=total_errors / total_matches if total_matches else 0.0,
                average_double_faults=(
                    total_double_faults / total_matches if total_matches else 0.0
                ),
                average_net_play_rate=(
                    sum(net_rates) / len(net_rates) if net_rates else None
                ),
            )

    async def get_doubles_player_stats(
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
                .where(Match.match_type == MATCH_TYPE_DOUBLES)
                .where(MatchPlayerStat.normalized_player_name == normalized_name)
                .where(Match.status == "confirmed")
                .order_by(Match.confirmed_at.desc(), Match.id.desc(), MatchPlayerStat.player_slot.asc())
            )
            rows = (await session.execute(stmt)).all()
            if not rows:
                raise QueryError(f"未找到昵称 `{game_nickname.strip()}` 的双打记录。")

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
            max_serve_speeds = [
                stat.max_serve_speed_kmh
                for stat, _match in rows
                if stat.max_serve_speed_kmh is not None
            ]

            return PlayerStatsSummary(
                display_name=rows[0][0].raw_player_name,
                total_matches=total_matches,
                wins=wins,
                losses=total_matches - wins,
                win_rate=wins / total_matches if total_matches else 0.0,
                average_points_won=total_points / total_matches if total_matches else 0.0,
                average_winners=total_winners / total_matches if total_matches else 0.0,
                average_serve_points_won=(
                    total_serve_points / total_matches if total_matches else 0.0
                ),
                average_errors=total_errors / total_matches if total_matches else 0.0,
                average_double_faults=(
                    total_double_faults / total_matches if total_matches else 0.0
                ),
                average_net_play_rate=(
                    sum(net_rates) / len(net_rates) if net_rates else None
                ),
                average_max_serve_speed_kmh=(
                    sum(max_serve_speeds) / len(max_serve_speeds) if max_serve_speeds else None
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
                .where(Match.match_type == MATCH_TYPE_SINGLES)
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

    async def get_doubles_recent_matches(
        self,
        *,
        platform: str,
        external_group_id: str,
        game_nickname: str,
        limit: int = 5,
    ) -> list[DoublesRecentMatchItem]:
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
                .where(Match.match_type == MATCH_TYPE_DOUBLES)
                .where(MatchPlayerStat.normalized_player_name == normalized_name)
                .where(Match.status == "confirmed")
                .order_by(Match.confirmed_at.desc(), Match.id.desc(), MatchPlayerStat.player_slot.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
            if not rows:
                raise QueryError(f"未找到昵称 `{game_nickname.strip()}` 的双打记录。")

            results: list[DoublesRecentMatchItem] = []
            for stat, match in rows:
                all_stats_stmt = (
                    select(MatchPlayerStat)
                    .where(MatchPlayerStat.match_id == match.id)
                    .order_by(MatchPlayerStat.side.asc(), MatchPlayerStat.player_slot.asc())
                )
                all_stats = list((await session.scalars(all_stats_stmt)).all())
                teammate = next(
                    (
                        item for item in all_stats
                        if item.side == stat.side and item.player_slot != stat.player_slot
                    ),
                    None,
                )
                opponents = [item for item in all_stats if item.side != stat.side]
                results.append(
                    DoublesRecentMatchItem(
                        match_code=match.match_code,
                        confirmed_at=match.confirmed_at,
                        is_winner=stat.is_winner,
                        teammate_name=teammate.raw_player_name if teammate is not None else "未知队友",
                        opponent_names=[item.raw_player_name for item in opponents],
                        team_points_won=self._team_points_total(all_stats, side=stat.side),
                        opponent_team_points_won=self._team_points_total(
                            all_stats,
                            side=1 if stat.side == 2 else 2,
                        ),
                        player_points_won=stat.points_won,
                        duration_seconds=match.duration_seconds,
                    )
                )
            return results

    def _team_points_total(self, stats: list[MatchPlayerStat], *, side: int) -> int | None:
        team_stats = [stat for stat in stats if stat.side == side]
        if not team_stats:
            return None
        if any(stat.points_won is None for stat in team_stats):
            return None
        return sum(stat.points_won or 0 for stat in team_stats)
