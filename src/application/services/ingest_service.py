import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from ..dto.ingest import IngestPlayerPreview, IngestPreview
from ...infrastructure.config.config_manager import ConfigManager
from ...infrastructure.llm.multimodal_extractor import MultimodalExtractor
from ...infrastructure.persistence.db import DatabaseManager
from ...infrastructure.persistence.models import Group, Match, MatchPlayerStat
from ...infrastructure.storage.image_store import ImageStore
from ...shared.match_types import MATCH_TYPE_SINGLES
from ...shared.text import normalize_name
from ...shared.time import utc_now


class IngestService:
    def __init__(
        self,
        db: DatabaseManager,
        config_manager: ConfigManager,
        extractor: MultimodalExtractor,
        image_store: ImageStore,
    ):
        self._db = db
        self._config_manager = config_manager
        self._extractor = extractor
        self._image_store = image_store

    async def ingest(
        self,
        *,
        match_type: str = MATCH_TYPE_SINGLES,
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
            match_type=match_type,
            unified_msg_origin=unified_msg_origin,
            image_path=saved_image.saved_path,
        )
        missing_fields = list(extraction.missing_fields)
        winner_side = extraction.normalized_payload.get("winner_side")
        auto_confirmed = not missing_fields and winner_side in {1, 2}

        expires_at = utc_now() + timedelta(
            hours=self._config_manager.get_pending_expire_hours()
        )

        async with self._db.session() as session:
            group = await self._get_or_create_group(
                session=session,
                platform=platform,
                external_group_id=external_group_id,
                group_name=group_name,
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
                match_type=match_type,
                status="confirmed" if auto_confirmed else "pending",
                submitted_by_user_id=platform_user_id,
                submitted_by_name=submitted_by_name,
                source_image_path=saved_image.saved_path,
                source_image_sha256=saved_image.sha256,
                raw_extraction_json=extraction.raw_text,
                normalized_json=json.dumps(extraction.normalized_payload, ensure_ascii=False),
                missing_fields_json=json.dumps(missing_fields, ensure_ascii=False),
                duplicate_of_match_id=duplicate_of_match_id,
                set_count=extraction.normalized_payload.get("set_count"),
                game_count=extraction.normalized_payload.get("game_count"),
                duration_seconds=extraction.normalized_payload.get("duration_seconds"),
                max_rally_count=extraction.normalized_payload.get("max_rally_count"),
                expires_at=None if auto_confirmed else expires_at,
                confirmed_at=utc_now() if auto_confirmed else None,
            )
            session.add(match)
            await session.flush()

            players_preview: list[IngestPlayerPreview] = []
            for index, player_payload in enumerate(extraction.normalized_payload["players"], start=1):
                player_slot = player_payload.get("player_slot") or index
                stat = MatchPlayerStat(
                    match_id=match.id,
                    side=player_payload["side"],
                    player_slot=player_slot,
                    raw_player_name=player_payload["name"],
                    normalized_player_name=normalize_name(player_payload["name"]),
                    is_winner=winner_side == player_payload["side"],
                    points_won=player_payload.get("points_won"),
                    winners=player_payload.get("winners"),
                    serve_points_won=player_payload.get("serve_points_won"),
                    errors=player_payload.get("errors"),
                    double_faults=player_payload.get("double_faults"),
                    net_play_rate=player_payload.get("net_play_rate"),
                    max_serve_speed_kmh=player_payload.get("max_serve_speed_kmh"),
                )
                session.add(stat)
                players_preview.append(
                    IngestPlayerPreview(
                        side=player_payload["side"],
                        player_slot=player_slot,
                        raw_name=player_payload["name"],
                        points_won=player_payload.get("points_won"),
                        winners=player_payload.get("winners"),
                        serve_points_won=player_payload.get("serve_points_won"),
                        errors=player_payload.get("errors"),
                        double_faults=player_payload.get("double_faults"),
                        net_play_rate=player_payload.get("net_play_rate"),
                        max_serve_speed_kmh=player_payload.get("max_serve_speed_kmh"),
                    )
                )

            await session.commit()

        return IngestPreview(
            match_code=match_code,
            match_type=match_type,
            status="confirmed" if auto_confirmed else "pending",
            players=players_preview,
            set_count=extraction.normalized_payload.get("set_count"),
            game_count=extraction.normalized_payload.get("game_count"),
            duration_seconds=extraction.normalized_payload.get("duration_seconds"),
            max_rally_count=extraction.normalized_payload.get("max_rally_count"),
            missing_fields=missing_fields,
            duplicate_hint=duplicate_of_match_id is not None,
            expires_at=None if auto_confirmed else expires_at,
            auto_confirmed=auto_confirmed,
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
        now = utc_now()
        return f"TEN-{now:%Y%m%d-%H%M%S}-{uuid4().hex[:4].upper()}"
