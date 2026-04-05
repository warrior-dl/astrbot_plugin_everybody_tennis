import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from .identity_service import IdentityService
from ...infrastructure.persistence.db import DatabaseManager
from ...infrastructure.persistence.models import Group, Match, MatchPlayerStat
from ...shared.text import normalize_name


class ConfirmationError(Exception):
    pass


@dataclass(slots=True)
class ConfirmationResult:
    match_code: str
    status: str
    message: str


class ConfirmationService:
    def __init__(self, db: DatabaseManager, identity_service: IdentityService):
        self._db = db
        self._identity_service = identity_service

    async def confirm(
        self,
        *,
        platform: str,
        external_group_id: str,
        operator_user_id: str,
        match_code: str,
    ) -> ConfirmationResult:
        async with self._db.session() as session:
            group = await self._get_group(
                session=session,
                platform=platform,
                external_group_id=external_group_id,
            )
            if group is None:
                raise ConfirmationError("当前群没有任何录入记录。")

            match = await self._get_match(
                session=session,
                group_id=group.id,
                match_code=match_code,
            )
            if match is None:
                raise ConfirmationError("未找到对应记录号。")
            if match.submitted_by_user_id != operator_user_id:
                raise ConfirmationError("当前版本仅允许提交人确认自己的记录。")
            if match.status != "pending":
                raise ConfirmationError(f"该记录当前状态为 {match.status}，不能再次确认。")

            if match.expires_at is not None and match.expires_at <= datetime.utcnow():
                match.status = "expired"
                await session.commit()
                raise ConfirmationError("该记录已过期，请重新录入。")

            stats = await self._get_match_stats(session=session, match_id=match.id)
            alias_resolution = await self._identity_service.resolve_aliases(
                platform=platform,
                external_group_id=external_group_id,
                aliases=[stat.raw_player_name for stat in stats],
                session=session,
            )
            for stat in stats:
                resolved = alias_resolution.get(normalize_name(stat.raw_player_name))
                if resolved is not None:
                    stat.player_id = resolved.id

            missing_fields = self._load_missing_fields(match.missing_fields_json)
            unresolved_names = [stat.raw_player_name for stat in stats if stat.player_id is None]
            if unresolved_names:
                raise ConfirmationError(
                    "仍有玩家未绑定昵称: " + ", ".join(unresolved_names)
                )
            if missing_fields:
                raise ConfirmationError(
                    "当前记录字段不完整，缺失: " + ", ".join(missing_fields)
                )

            winner_stat = next((stat for stat in stats if stat.is_winner), None)
            loser_stat = next((stat for stat in stats if not stat.is_winner), None)
            if winner_stat is None or loser_stat is None:
                raise ConfirmationError("当前记录无法确定胜负方。")

            match.winner_player_id = winner_stat.player_id
            match.loser_player_id = loser_stat.player_id
            match.status = "confirmed"
            match.confirmed_at = datetime.utcnow()
            await session.commit()
            return ConfirmationResult(
                match_code=match.match_code,
                status=match.status,
                message="记录已确认入库。",
            )

    async def cancel(
        self,
        *,
        platform: str,
        external_group_id: str,
        operator_user_id: str,
        match_code: str,
    ) -> ConfirmationResult:
        async with self._db.session() as session:
            group = await self._get_group(
                session=session,
                platform=platform,
                external_group_id=external_group_id,
            )
            if group is None:
                raise ConfirmationError("当前群没有任何录入记录。")

            match = await self._get_match(
                session=session,
                group_id=group.id,
                match_code=match_code,
            )
            if match is None:
                raise ConfirmationError("未找到对应记录号。")
            if match.submitted_by_user_id != operator_user_id:
                raise ConfirmationError("当前版本仅允许提交人取消自己的记录。")
            if match.status != "pending":
                raise ConfirmationError(f"该记录当前状态为 {match.status}，不能取消。")

            match.status = "cancelled"
            match.cancelled_at = datetime.utcnow()
            await session.commit()
            return ConfirmationResult(
                match_code=match.match_code,
                status=match.status,
                message="记录已取消，不会进入正式统计。",
            )

    async def _get_group(self, *, session, platform: str, external_group_id: str) -> Group | None:
        stmt = (
            select(Group)
            .where(Group.platform == platform)
            .where(Group.external_group_id == external_group_id)
        )
        return await session.scalar(stmt)

    async def _get_match(self, *, session, group_id: int, match_code: str) -> Match | None:
        stmt = (
            select(Match)
            .where(Match.group_id == group_id)
            .where(Match.match_code == match_code)
        )
        return await session.scalar(stmt)

    async def _get_match_stats(self, *, session, match_id: int) -> list[MatchPlayerStat]:
        stmt = (
            select(MatchPlayerStat)
            .where(MatchPlayerStat.match_id == match_id)
            .order_by(MatchPlayerStat.side.asc())
        )
        result = await session.scalars(stmt)
        return list(result.all())

    def _load_missing_fields(self, payload: str | None) -> list[str]:
        if not payload:
            return []
        try:
            loaded = json.loads(payload)
        except json.JSONDecodeError:
            return []
        if not isinstance(loaded, list):
            return []
        return [str(item) for item in loaded]
