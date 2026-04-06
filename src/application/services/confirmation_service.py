from dataclasses import dataclass

from sqlalchemy import select

from ...infrastructure.persistence.db import DatabaseManager
from ...infrastructure.persistence.models import MatchPlayerStat
from ...shared.time import utc_now
from ._scope import GroupScopedLookup


class ConfirmationError(Exception):
    pass


@dataclass(slots=True)
class ConfirmationResult:
    match_code: str
    status: str
    message: str


class ConfirmationService(GroupScopedLookup):
    def __init__(self, db: DatabaseManager):
        self._db = db

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
            if match.status == "confirmed":
                raise ConfirmationError("该记录已自动入库，无需再次确认。")
            if match.status != "pending":
                raise ConfirmationError(f"该记录当前状态为 {match.status}，不能再次确认。")

            if match.expires_at is not None and match.expires_at <= utc_now():
                match.status = "expired"
                await session.commit()
                raise ConfirmationError("该记录已过期，请重新录入。")

            stats = await self._get_match_stats(session=session, match_id=match.id)

            winner_stat = next((stat for stat in stats if stat.is_winner), None)
            loser_stat = next((stat for stat in stats if not stat.is_winner), None)
            if winner_stat is None or loser_stat is None:
                raise ConfirmationError("当前记录无法确定胜负方。")

            match.status = "confirmed"
            match.confirmed_at = utc_now()
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
            if match.status not in {"pending", "confirmed"}:
                raise ConfirmationError(f"该记录当前状态为 {match.status}，不能取消。")

            original_status = match.status
            match.status = "cancelled"
            match.cancelled_at = utc_now()
            if original_status == "confirmed":
                match.confirmed_at = None
            await session.commit()
            return ConfirmationResult(
                match_code=match.match_code,
                status=match.status,
                message="记录已取消，后续统计将不再包含该记录。",
            )

    async def _get_match_stats(self, *, session, match_id: int) -> list[MatchPlayerStat]:
        stmt = (
            select(MatchPlayerStat)
            .where(MatchPlayerStat.match_id == match_id)
            .order_by(MatchPlayerStat.side.asc(), MatchPlayerStat.player_slot.asc())
        )
        result = await session.scalars(stmt)
        return list(result.all())
