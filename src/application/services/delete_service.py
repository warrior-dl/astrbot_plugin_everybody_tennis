from dataclasses import dataclass

from ...infrastructure.config.config_manager import ConfigManager
from ...infrastructure.persistence.db import DatabaseManager
from ...shared.time import utc_now
from ._scope import GroupScopedLookup


class DeleteError(Exception):
    pass


@dataclass(slots=True)
class DeleteResult:
    match_code: str
    status: str
    message: str


class DeleteService(GroupScopedLookup):
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
            match.deleted_at = utc_now()
            await session.commit()
            return DeleteResult(
                match_code=match.match_code,
                status=match.status,
                message="记录已删除，后续统计将自动忽略该记录。",
            )
