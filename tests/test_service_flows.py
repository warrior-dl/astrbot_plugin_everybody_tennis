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


class FakeExtractor:
    def __init__(self, result: ExtractionResult):
        self._result = result

    async def extract(self, *, unified_msg_origin: str, image_path: str) -> ExtractionResult:
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


if __name__ == "__main__":
    unittest.main()
