from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select

from src.infrastructure.persistence.models import Group, Player, PlayerAlias
from src.infrastructure.persistence.db import DatabaseManager
from src.shared.text import normalize_name


class AliasConflictError(Exception):
    def __init__(self, alias: str):
        super().__init__(f"alias conflict: {alias}")
        self.alias = alias


@dataclass(slots=True)
class BindAliasResult:
    alias: str
    created: bool


@dataclass(slots=True)
class ResolvedAlias:
    id: int
    display_name: str
    platform_user_id: str


class IdentityService:
    def __init__(self, db: DatabaseManager):
        self._db = db

    async def bind_alias(
        self,
        *,
        platform: str,
        external_group_id: str,
        group_name: str,
        platform_user_id: str,
        display_name: str,
        alias: str,
    ) -> BindAliasResult:
        normalized_alias = normalize_name(alias)
        if not normalized_alias:
            raise ValueError("游戏昵称不能为空。")

        async with self._db.session() as session:
            group = await self._get_or_create_group(
                session=session,
                platform=platform,
                external_group_id=external_group_id,
                group_name=group_name,
            )
            player = await self._get_or_create_player(
                session=session,
                group_id=group.id,
                platform_user_id=platform_user_id,
                display_name=display_name,
            )

            conflict_stmt = (
                select(PlayerAlias)
                .where(PlayerAlias.group_id == group.id)
                .where(PlayerAlias.normalized_alias == normalized_alias)
                .where(PlayerAlias.player_id != player.id)
            )
            conflict = await session.scalar(conflict_stmt)
            if conflict is not None:
                raise AliasConflictError(alias)

            existing_alias_stmt = (
                select(PlayerAlias)
                .where(PlayerAlias.player_id == player.id)
                .where(PlayerAlias.normalized_alias == normalized_alias)
            )
            existing_alias = await session.scalar(existing_alias_stmt)
            if existing_alias is not None:
                await session.commit()
                return BindAliasResult(alias=existing_alias.alias, created=False)

            session.add(
                PlayerAlias(
                    group_id=group.id,
                    player_id=player.id,
                    alias=alias.strip(),
                    normalized_alias=normalized_alias,
                )
            )
            await session.commit()
            return BindAliasResult(alias=alias.strip(), created=True)

    async def list_aliases(
        self,
        *,
        platform: str,
        external_group_id: str,
        platform_user_id: str,
    ) -> Sequence[str]:
        async with self._db.session() as session:
            group_stmt = (
                select(Group)
                .where(Group.platform == platform)
                .where(Group.external_group_id == external_group_id)
            )
            group = await session.scalar(group_stmt)
            if group is None:
                return []

            player_stmt = (
                select(Player)
                .where(Player.group_id == group.id)
                .where(Player.platform_user_id == platform_user_id)
            )
            player = await session.scalar(player_stmt)
            if player is None:
                return []

            alias_stmt = (
                select(PlayerAlias.alias)
                .where(PlayerAlias.player_id == player.id)
                .order_by(PlayerAlias.created_at.asc())
            )
            result = await session.scalars(alias_stmt)
            return list(result.all())

    async def resolve_aliases(
        self,
        *,
        platform: str,
        external_group_id: str,
        aliases: Sequence[str],
        session=None,
    ) -> dict[str, ResolvedAlias]:
        if session is None:
            async with self._db.session() as managed_session:
                return await self.resolve_aliases(
                    platform=platform,
                    external_group_id=external_group_id,
                    aliases=aliases,
                    session=managed_session,
                )

        group_stmt = (
            select(Group)
            .where(Group.platform == platform)
            .where(Group.external_group_id == external_group_id)
        )
        group = await session.scalar(group_stmt)
        if group is None:
            return {}

        normalized_aliases = [normalize_name(alias) for alias in aliases if normalize_name(alias)]
        if not normalized_aliases:
            return {}

        stmt = (
            select(PlayerAlias, Player)
            .join(Player, PlayerAlias.player_id == Player.id)
            .where(PlayerAlias.group_id == group.id)
            .where(PlayerAlias.normalized_alias.in_(normalized_aliases))
        )
        rows = await session.execute(stmt)
        resolved: dict[str, ResolvedAlias] = {}
        for alias_row, player_row in rows.all():
            resolved[alias_row.normalized_alias] = ResolvedAlias(
                id=player_row.id,
                display_name=player_row.display_name,
                platform_user_id=player_row.platform_user_id,
            )
        return resolved

    async def get_player_by_platform_user(
        self,
        *,
        platform: str,
        external_group_id: str,
        platform_user_id: str,
        session=None,
    ) -> Player | None:
        if session is None:
            async with self._db.session() as managed_session:
                return await self.get_player_by_platform_user(
                    platform=platform,
                    external_group_id=external_group_id,
                    platform_user_id=platform_user_id,
                    session=managed_session,
                )

        group_stmt = (
            select(Group)
            .where(Group.platform == platform)
            .where(Group.external_group_id == external_group_id)
        )
        group = await session.scalar(group_stmt)
        if group is None:
            return None

        player_stmt = (
            select(Player)
            .where(Player.group_id == group.id)
            .where(Player.platform_user_id == platform_user_id)
        )
        return await session.scalar(player_stmt)

    async def _get_or_create_group(
        self,
        *,
        session,
        platform: str,
        external_group_id: str,
        group_name: str,
    ) -> Group:
        stmt = (
            select(Group)
            .where(Group.platform == platform)
            .where(Group.external_group_id == external_group_id)
        )
        group = await session.scalar(stmt)
        if group is not None:
            if group_name and group.group_name != group_name:
                group.group_name = group_name
            return group

        group = Group(
            platform=platform,
            external_group_id=external_group_id,
            group_name=group_name or "",
        )
        session.add(group)
        await session.flush()
        return group

    async def _get_or_create_player(
        self,
        *,
        session,
        group_id: int,
        platform_user_id: str,
        display_name: str,
    ) -> Player:
        stmt = (
            select(Player)
            .where(Player.group_id == group_id)
            .where(Player.platform_user_id == platform_user_id)
        )
        player = await session.scalar(stmt)
        normalized_display_name = normalize_name(display_name)
        if player is not None:
            player.display_name = display_name
            player.normalized_display_name = normalized_display_name
            return player

        player = Player(
            group_id=group_id,
            platform_user_id=platform_user_id,
            display_name=display_name,
            normalized_display_name=normalized_display_name,
        )
        session.add(player)
        await session.flush()
        return player
