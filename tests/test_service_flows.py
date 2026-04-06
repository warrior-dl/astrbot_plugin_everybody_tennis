import os
import tempfile
import unittest
from pathlib import Path

from src.application.services.confirmation_service import ConfirmationService
from src.application.services.ingest_service import IngestService
from src.application.services.query_service import QueryError, QueryService
from src.application.services.ranking_service import RankingService
from src.infrastructure.config.config_manager import ConfigManager
from src.infrastructure.llm.multimodal_extractor import ExtractionResult
from src.infrastructure.persistence.db import DatabaseManager
from src.infrastructure.storage.image_store import ImageStore
from src.shared.match_types import MATCH_TYPE_DOUBLES, MATCH_TYPE_SINGLES


class FakeExtractor:
    def __init__(self, result: ExtractionResult):
        self._result = result

    async def extract(
        self,
        *,
        match_type: str,
        unified_msg_origin: str,
        image_path: str,
    ) -> ExtractionResult:
        return self._result


class TennisServiceFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._old_astrbot_root = os.environ.get("ASTRBOT_ROOT")
        os.environ["ASTRBOT_ROOT"] = self._temp_dir.name

        self._plugin_name = "astrbot_plugin_everybody_tennis_test"
        self._config = ConfigManager(
            {
                "storage": {"pending_expire_hours": 24},
                "ranking": {
                    "min_matches_for_win_rate": 1,
                    "default_top_n": 10,
                },
            }
        )
        self._db = DatabaseManager(self._plugin_name)
        await self._db.initialize()
        self._image_store = ImageStore(self._plugin_name)
        self._query_service = QueryService(self._db)
        self._confirmation_service = ConfirmationService(self._db)
        self._ranking_service = RankingService(self._db, self._config)

        self._source_image = Path(self._temp_dir.name) / "input.jpg"
        self._source_image.write_bytes(b"fake-image-bytes")

    async def asyncTearDown(self):
        await self._db.close()
        if self._old_astrbot_root is None:
            os.environ.pop("ASTRBOT_ROOT", None)
        else:
            os.environ["ASTRBOT_ROOT"] = self._old_astrbot_root
        self._temp_dir.cleanup()

    async def test_complete_record_auto_confirms_and_can_be_cancelled(self):
        ingest_service = IngestService(
            db=self._db,
            config_manager=self._config,
            extractor=FakeExtractor(self._build_extraction()),
            image_store=self._image_store,
        )

        preview = await ingest_service.ingest(
            match_type=MATCH_TYPE_SINGLES,
            platform="test",
            external_group_id="group-1",
            group_name="Test Group",
            platform_user_id="user-1",
            submitted_by_name="Alice",
            unified_msg_origin="umo-1",
            source_image_path=str(self._source_image),
        )

        self.assertTrue(preview.auto_confirmed)
        self.assertEqual(preview.status, "confirmed")

        summary = await self._query_service.get_player_stats(
            platform="test",
            external_group_id="group-1",
            game_nickname="ntr",
        )
        self.assertEqual(summary.total_matches, 1)
        self.assertEqual(summary.wins, 1)
        self.assertAlmostEqual(summary.average_points_won, 24.0)
        self.assertAlmostEqual(summary.average_winners, 10.0)

        metric_key, entries = await self._ranking_service.get_ranking(
            platform="test",
            external_group_id="group-1",
            metric="得分",
            top_n=5,
        )
        self.assertEqual(metric_key, "avg_points")
        self.assertEqual(entries[0].display_name, "ntr")
        self.assertAlmostEqual(entries[0].value, 24.0)

        cancel_result = await self._confirmation_service.cancel(
            platform="test",
            external_group_id="group-1",
            operator_user_id="user-1",
            match_code=preview.match_code,
        )
        self.assertEqual(cancel_result.status, "cancelled")

        with self.assertRaises(QueryError):
            await self._query_service.get_player_stats(
                platform="test",
                external_group_id="group-1",
                game_nickname="ntr",
            )

    async def test_pending_record_with_missing_fields_can_be_confirmed(self):
        extraction = self._build_extraction(missing_fields=["max_rally_count"])
        extraction.normalized_payload["max_rally_count"] = None

        ingest_service = IngestService(
            db=self._db,
            config_manager=self._config,
            extractor=FakeExtractor(extraction),
            image_store=self._image_store,
        )

        preview = await ingest_service.ingest(
            match_type=MATCH_TYPE_SINGLES,
            platform="test",
            external_group_id="group-2",
            group_name="Test Group",
            platform_user_id="user-2",
            submitted_by_name="Bob",
            unified_msg_origin="umo-2",
            source_image_path=str(self._source_image),
        )

        self.assertFalse(preview.auto_confirmed)
        self.assertEqual(preview.status, "pending")
        self.assertEqual(preview.missing_fields, ["max_rally_count"])

        confirm_result = await self._confirmation_service.confirm(
            platform="test",
            external_group_id="group-2",
            operator_user_id="user-2",
            match_code=preview.match_code,
        )
        self.assertEqual(confirm_result.status, "confirmed")

        summary = await self._query_service.get_player_stats(
            platform="test",
            external_group_id="group-2",
            game_nickname="ntr",
        )
        self.assertEqual(summary.total_matches, 1)
        self.assertAlmostEqual(summary.average_points_won, 24.0)

    async def test_doubles_ingest_is_stored_and_does_not_pollute_singles_stats(self):
        ingest_service = IngestService(
            db=self._db,
            config_manager=self._config,
            extractor=FakeExtractor(self._build_doubles_extraction()),
            image_store=self._image_store,
        )

        preview = await ingest_service.ingest(
            match_type=MATCH_TYPE_DOUBLES,
            platform="test",
            external_group_id="group-3",
            group_name="Test Group",
            platform_user_id="user-3",
            submitted_by_name="Carol",
            unified_msg_origin="umo-3",
            source_image_path=str(self._source_image),
        )

        self.assertEqual(preview.match_type, MATCH_TYPE_DOUBLES)
        self.assertEqual(preview.status, "confirmed")
        self.assertTrue(preview.auto_confirmed)
        self.assertEqual(len(preview.players), 4)
        self.assertEqual([player.side for player in preview.players], [1, 1, 2, 2])
        self.assertEqual(preview.players[0].max_serve_speed_kmh, 131)
        self.assertEqual(preview.players[2].max_serve_speed_kmh, 145)

        with self.assertRaises(QueryError):
            await self._query_service.get_player_stats(
                platform="test",
                external_group_id="group-3",
                game_nickname="幸",
            )

    def _build_extraction(self, *, missing_fields: list[str] | None = None) -> ExtractionResult:
        payload = {
            "players": [
                {
                    "side": 1,
                    "name": "ntr",
                    "points_won": 24,
                    "winners": 10,
                    "serve_points_won": 8,
                    "errors": 3,
                    "double_faults": 1,
                    "net_play_rate": 0.5,
                },
                {
                    "side": 2,
                    "name": "幸(18级)",
                    "points_won": 12,
                    "winners": 4,
                    "serve_points_won": 3,
                    "errors": 6,
                    "double_faults": 2,
                    "net_play_rate": 0.25,
                },
            ],
            "set_count": 1,
            "game_count": 6,
            "duration_seconds": 233,
            "max_rally_count": 4,
            "winner_side": 1,
            "missing_fields": list(missing_fields or []),
            "is_complete": not missing_fields,
        }
        return ExtractionResult(
            raw_text="{}",
            normalized_payload=payload,
            missing_fields=list(missing_fields or []),
        )

    def _build_doubles_extraction(self) -> ExtractionResult:
        payload = {
            "match_type": MATCH_TYPE_DOUBLES,
            "players": [
                {
                    "side": 1,
                    "player_slot": 1,
                    "name": "幸",
                    "points_won": 11,
                    "winners": 8,
                    "serve_points_won": 0,
                    "errors": 2,
                    "double_faults": 0,
                    "net_play_rate": 0.0,
                    "max_serve_speed_kmh": 131,
                },
                {
                    "side": 1,
                    "player_slot": 2,
                    "name": "半梦",
                    "points_won": 13,
                    "winners": 9,
                    "serve_points_won": 0,
                    "errors": 1,
                    "double_faults": 0,
                    "net_play_rate": 0.0,
                    "max_serve_speed_kmh": 135,
                },
                {
                    "side": 2,
                    "player_slot": 3,
                    "name": "Days-X",
                    "points_won": 5,
                    "winners": 3,
                    "serve_points_won": 1,
                    "errors": 3,
                    "double_faults": 0,
                    "net_play_rate": 0.0,
                    "max_serve_speed_kmh": 145,
                },
                {
                    "side": 2,
                    "player_slot": 4,
                    "name": "COM",
                    "points_won": 4,
                    "winners": 2,
                    "serve_points_won": 0,
                    "errors": 4,
                    "double_faults": 0,
                    "net_play_rate": 0.381,
                    "max_serve_speed_kmh": 134,
                },
            ],
            "set_count": 1,
            "game_count": 6,
            "duration_seconds": 399,
            "max_rally_count": 30,
            "winner_side": 1,
            "missing_fields": [],
            "is_complete": True,
        }
        return ExtractionResult(
            raw_text="{}",
            normalized_payload=payload,
            missing_fields=[],
        )


if __name__ == "__main__":
    unittest.main()
