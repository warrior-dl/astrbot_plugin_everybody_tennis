from collections import defaultdict

from sqlalchemy import select

from ..dto.ranking import RankingEntry
from ...infrastructure.config.config_manager import ConfigManager
from ...infrastructure.persistence.db import DatabaseManager
from ...infrastructure.persistence.models import Match, MatchPlayerStat
from ._scope import GroupScopedLookup


class RankingError(Exception):
    pass


class RankingService(GroupScopedLookup):
    METRIC_ALIASES = {
        "胜场": "wins",
        "wins": "wins",
        "胜率": "win_rate",
        "winrate": "win_rate",
        "win_rate": "win_rate",
        "场次": "matches",
        "matches": "matches",
        "场均得分": "avg_points",
        "得分": "avg_points",
        "avg_points": "avg_points",
        "points": "avg_points",
        "场均胜球": "avg_winners",
        "胜球": "avg_winners",
        "avg_winners": "avg_winners",
        "winners": "avg_winners",
    }

    def __init__(self, db: DatabaseManager, config_manager: ConfigManager):
        self._db = db
        self._config_manager = config_manager

    async def get_ranking(
        self,
        *,
        platform: str,
        external_group_id: str,
        metric: str,
        top_n: int | None = None,
    ) -> tuple[str, list[RankingEntry]]:
        metric_key = self.METRIC_ALIASES.get(metric.strip().lower()) or self.METRIC_ALIASES.get(metric.strip())
        if metric_key is None:
            raise RankingError("不支持的排行指标，可用：胜场、胜率、场次、场均得分、场均胜球。")

        limit = top_n or self._config_manager.get_default_top_n()
        async with self._db.session() as session:
            group = await self._get_group(
                session=session,
                platform=platform,
                external_group_id=external_group_id,
            )
            if group is None:
                raise RankingError("当前群还没有任何比赛记录。")

            stmt = (
                select(MatchPlayerStat, Match)
                .join(Match, MatchPlayerStat.match_id == Match.id)
                .where(Match.group_id == group.id)
                .where(Match.status == "confirmed")
                .order_by(Match.confirmed_at.desc(), Match.id.desc(), MatchPlayerStat.side.asc())
            )
            rows = (await session.execute(stmt)).all()
            if not rows:
                raise RankingError("当前群还没有已确认的比赛记录。")

            aggregates: dict[str, dict] = defaultdict(
                lambda: {
                    "display_name": "",
                    "matches": 0,
                    "wins": 0,
                    "points": 0,
                    "winners": 0,
                }
            )
            for stat, _match in rows:
                player_key = stat.normalized_player_name
                if not player_key:
                    continue
                bucket = aggregates[player_key]
                if not bucket["display_name"]:
                    bucket["display_name"] = stat.raw_player_name
                bucket["matches"] += 1
                bucket["wins"] += 1 if stat.is_winner else 0
                bucket["points"] += stat.points_won or 0
                bucket["winners"] += stat.winners or 0

            min_matches = self._config_manager.get_min_matches_for_win_rate()
            prepared: list[RankingEntry] = []
            for bucket in aggregates.values():
                if metric_key == "win_rate" and bucket["matches"] < min_matches:
                    continue
                value = self._metric_value(metric_key, bucket)
                prepared.append(
                    RankingEntry(
                        rank=0,
                        display_name=bucket["display_name"],
                        matches=bucket["matches"],
                        wins=bucket["wins"],
                        value=value,
                        metric_key=metric_key,
                    )
                )

            if not prepared:
                raise RankingError("当前排行没有满足条件的玩家。")

            prepared.sort(
                key=lambda item: (item.value, item.wins, item.matches, item.display_name),
                reverse=True,
            )
            ranked = [
                RankingEntry(
                    rank=index + 1,
                    display_name=item.display_name,
                    matches=item.matches,
                    wins=item.wins,
                    value=item.value,
                    metric_key=item.metric_key,
                )
                for index, item in enumerate(prepared[:limit])
            ]
            return metric_key, ranked

    def _metric_value(self, metric_key: str, bucket: dict) -> float:
        if metric_key == "wins":
            return float(bucket["wins"])
        if metric_key == "win_rate":
            return bucket["wins"] / bucket["matches"] if bucket["matches"] else 0.0
        if metric_key == "matches":
            return float(bucket["matches"])
        if metric_key == "avg_points":
            return bucket["points"] / bucket["matches"] if bucket["matches"] else 0.0
        if metric_key == "avg_winners":
            return bucket["winners"] / bucket["matches"] if bucket["matches"] else 0.0
        raise RankingError("未知排行指标。")
