from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from src.infrastructure.config.config_manager import ConfigManager
from src.infrastructure.persistence.db import DatabaseManager
from src.infrastructure.persistence.models import Group, Match


class DeleteError(Exception):
    pass


@dataclass(slots=True)
class DeleteResult:
    match_code: str
    status: str
    message: str


class DeleteService:
    def __init__(self, db: DatabaseManager, config_manager: ConfigManager):
        self._db = db
        self._config_manager = config_manager

    async def delete_match(
        self,
        *,
        platform: str,
        external_group_id: str,
        operator_user_id: str,
        is_admin: bool,
        match_code: str,
    ) -> DeleteResult:
        async with self._db.session() as session:
            group = await self._get_group(
                session=session,
                platform=platform,
                external_group_id=external_group_id,
            )
            if group is None:
                raise DeleteError("当前群没有任何录入记录。")

            match = await self._get_match(
                session=session,
                group_id=group.id,
                match_code=match_code,
            )
            if match is None:
                raise DeleteError("未找到对应记录号。")
            if match.status == "deleted":
                raise DeleteError("该记录已经删除。")

            is_submitter = match.submitted_by_user_id == operator_user_id
            if is_admin:
                pass
            elif is_submitter and self._config_manager.allow_submitter_delete():
                pass
            else:
                raise DeleteError("只有提交人本人或管理员可以删除该记录。")

            match.status = "deleted"
            match.deleted_at = datetime.utcnow()
            await session.commit()
            return DeleteResult(
                match_code=match.match_code,
                status=match.status,
                message="记录已删除，后续统计将自动忽略该记录。",
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
