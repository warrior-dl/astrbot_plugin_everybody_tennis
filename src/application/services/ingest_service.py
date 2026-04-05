import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from ..dto.ingest import IngestPlayerPreview, IngestPreview
from .identity_service import IdentityService
from ...infrastructure.config.config_manager import ConfigManager
from ...infrastructure.llm.multimodal_extractor import MultimodalExtractor
from ...infrastructure.persistence.db import DatabaseManager
from ...infrastructure.persistence.models import Group, Match, MatchPlayerStat
from ...infrastructure.storage.image_store import ImageStore
from ...shared.text import normalize_name


class IngestService:
    def __init__(
        self,
        db: DatabaseManager,
        config_manager: ConfigManager,
        extractor: MultimodalExtractor,
        image_store: ImageStore,
        identity_service: IdentityService,
    ):
        self._db = db
        self._config_manager = config_manager
        self._extractor = extractor
        self._image_store = image_store
        self._identity_service = identity_service

    async def ingest(
        self,
        *,
        platform: str,
        external_group_id: str,
        group_name: str,
        platform_user_id: str,
        submitted_by_name: str,
        unified_msg_origin: str,
        source_image_path: str,
    ) -> IngestPreview:
        saved_image = await self._image_store.save_image(source_image_path)
        extraction = await self._extractor.extract(
            unified_msg_origin=unified_msg_origin,
            image_path=saved_image.saved_path,
        )

        expires_at = datetime.utcnow() + timedelta(
            hours=self._config_manager.get_pending_expire_hours()
        )

        async with self._db.session() as session:
            group = await self._get_or_create_group(
                session=session,
                platform=platform,
                external_group_id=external_group_id,
                group_name=group_name,
            )
            alias_resolution = await self._identity_service.resolve_aliases(
                platform=platform,
                external_group_id=external_group_id,
                aliases=[player["name"] for player in extraction.normalized_payload["players"]],
                session=session,
            )

            duplicate_of_match_id = await self._find_duplicate_match_id(
                session=session,
                group_id=group.id,
                source_image_sha256=saved_image.sha256,
            )
            match_code = self._generate_match_code()
            match = Match(
                match_code=match_code,
                group_id=group.id,
                status="pending",
                submitted_by_user_id=platform_user_id,
                submitted_by_name=submitted_by_name,
                source_image_path=saved_image.saved_path,
                source_image_sha256=saved_image.sha256,
                raw_extraction_json=extraction.raw_text,
                normalized_json=json.dumps(extraction.normalized_payload, ensure_ascii=False),
                missing_fields_json=json.dumps(extraction.missing_fields, ensure_ascii=False),
                duplicate_of_match_id=duplicate_of_match_id,
                set_count=extraction.normalized_payload.get("set_count"),
                game_count=extraction.normalized_payload.get("game_count"),
                duration_seconds=extraction.normalized_payload.get("duration_seconds"),
                max_rally_count=extraction.normalized_payload.get("max_rally_count"),
                expires_at=expires_at,
            )
            session.add(match)
            await session.flush()

            players_preview: list[IngestPlayerPreview] = []
            winner_side = extraction.normalized_payload.get("winner_side")
            for player_payload in extraction.normalized_payload["players"]:
                resolved_player = alias_resolution.get(
                    normalize_name(player_payload["name"])
                )
                stat = MatchPlayerStat(
                    match_id=match.id,
                    side=player_payload["side"],
                    raw_player_name=player_payload["name"],
                    normalized_player_name=normalize_name(player_payload["name"]),
                    player_id=resolved_player.id if resolved_player else None,
                    is_winner=winner_side == player_payload["side"],
                    points_won=player_payload.get("points_won"),
                    winners=player_payload.get("winners"),
                    serve_points_won=player_payload.get("serve_points_won"),
                    errors=player_payload.get("errors"),
                    double_faults=player_payload.get("double_faults"),
                    net_play_rate=player_payload.get("net_play_rate"),
                )
                session.add(stat)
                players_preview.append(
                    IngestPlayerPreview(
                        side=player_payload["side"],
                        raw_name=player_payload["name"],
                        resolved_display_name=resolved_player.display_name if resolved_player else None,
                        resolved=resolved_player is not None,
                        points_won=player_payload.get("points_won"),
                        winners=player_payload.get("winners"),
                        serve_points_won=player_payload.get("serve_points_won"),
                        errors=player_payload.get("errors"),
                        double_faults=player_payload.get("double_faults"),
                        net_play_rate=player_payload.get("net_play_rate"),
                    )
                )

            if len(players_preview) == 2 and winner_side in {1, 2}:
                winner_preview = next(
                    (player for player in players_preview if player.side == winner_side),
                    None,
                )
                loser_preview = next(
                    (player for player in players_preview if player.side != winner_side),
                    None,
                )
                if winner_preview and loser_preview:
                    if winner_preview.resolved_display_name:
                        match.winner_player_id = alias_resolution[
                            normalize_name(winner_preview.raw_name)
                        ].id
                    if loser_preview.resolved_display_name:
                        match.loser_player_id = alias_resolution[
                            normalize_name(loser_preview.raw_name)
                        ].id

            await session.commit()

        return IngestPreview(
            match_code=match_code,
            status="pending",
            players=players_preview,
            set_count=extraction.normalized_payload.get("set_count"),
            game_count=extraction.normalized_payload.get("game_count"),
            duration_seconds=extraction.normalized_payload.get("duration_seconds"),
            max_rally_count=extraction.normalized_payload.get("max_rally_count"),
            missing_fields=extraction.missing_fields,
            duplicate_hint=duplicate_of_match_id is not None,
            expires_at=expires_at,
        )

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

    async def _find_duplicate_match_id(
        self,
        *,
        session,
        group_id: int,
        source_image_sha256: str,
    ) -> int | None:
        stmt = (
            select(Match.id)
            .where(Match.group_id == group_id)
            .where(Match.source_image_sha256 == source_image_sha256)
            .where(Match.status != "deleted")
            .order_by(Match.created_at.desc())
            .limit(1)
        )
        return await session.scalar(stmt)

    def _generate_match_code(self) -> str:
        now = datetime.utcnow()
        return f"TEN-{now:%Y%m%d-%H%M%S}-{uuid4().hex[:4].upper()}"
