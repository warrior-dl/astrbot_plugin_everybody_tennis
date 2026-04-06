from sqlalchemy import select

from ...infrastructure.persistence.models import Group, Match


class GroupScopedLookup:
    async def _get_group(
        self,
        *,
        session,
        platform: str,
        external_group_id: str,
    ) -> Group | None:
        stmt = (
            select(Group)
            .where(Group.platform == platform)
            .where(Group.external_group_id == external_group_id)
        )
        return await session.scalar(stmt)

    async def _get_match(
        self,
        *,
        session,
        group_id: int,
        match_code: str,
    ) -> Match | None:
        stmt = (
            select(Match)
            .where(Match.group_id == group_id)
            .where(Match.match_code == match_code)
        )
        return await session.scalar(stmt)
