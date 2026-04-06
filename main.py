import asyncio

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .src.application.services.confirmation_service import (
    ConfirmationError,
    ConfirmationService,
)
from .src.application.services.ingest_service import IngestService
from .src.application.services.query_service import QueryError, QueryService
from .src.application.services.ranking_service import RankingError, RankingService
from .src.application.services.delete_service import DeleteError, DeleteService
from .src.infrastructure.config.config_manager import ConfigManager
from .src.infrastructure.llm.multimodal_extractor import ExtractionError, MultimodalExtractor
from .src.infrastructure.messaging.result_renderer import ResultRenderer
from .src.infrastructure.platform.message_parser import MessageParser, MessageParserError
from .src.infrastructure.persistence.db import DatabaseManager
from .src.infrastructure.storage.image_store import ImageStore
from .src.shared.match_types import MATCH_TYPE_DOUBLES, MATCH_TYPE_SINGLES

PLUGIN_NAME = "astrbot_plugin_everybody_tennis"


@register(
    PLUGIN_NAME,
    "OpenAI",
    "收集群内网球对战截图并沉淀统计数据",
    "0.1.0",
    "",
)
class EverybodyTennisPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._config_manager = ConfigManager(config)
        self._db = DatabaseManager(PLUGIN_NAME)
        self._message_parser = MessageParser()
        self._image_store = ImageStore(PLUGIN_NAME)
        self._extractor = MultimodalExtractor(self.context, self._config_manager)
        self._confirmation_service = ConfirmationService(
            db=self._db,
        )
        self._query_service = QueryService(
            db=self._db,
        )
        self._ranking_service = RankingService(
            db=self._db,
            config_manager=self._config_manager,
        )
        self._delete_service = DeleteService(
            db=self._db,
            config_manager=self._config_manager,
        )
        self._ingest_service = IngestService(
            db=self._db,
            config_manager=self._config_manager,
            extractor=self._extractor,
            image_store=self._image_store,
        )
        self._initialized = False
        self._terminating = False
        self._init_lock = asyncio.Lock()

    @filter.on_platform_loaded()
    async def on_platform_loaded(self):
        await self._run_initialization()

    async def _run_initialization(self):
        async with self._init_lock:
            if self._initialized or self._terminating:
                return
            if not self._config_manager.is_enabled():
                logger.info(f"{PLUGIN_NAME} is disabled by configuration")
                self._initialized = True
                return
            await self._db.initialize()
            self._initialized = True
            logger.info(f"{PLUGIN_NAME} initialization completed")

    async def _ensure_ready(self):
        await self._run_initialization()
        if self._terminating:
            raise RuntimeError("plugin is terminating")

    @filter.command_group("网球")
    def tennis(self):
        """网球战绩管理命令组"""

    @tennis.command("帮助", alias={"help", "帮助"})
    async def tennis_help(self, event: AstrMessageEvent):
        """查看插件帮助"""
        await self._ensure_ready()
        yield event.plain_result(ResultRenderer.help_text())

    @tennis.command("录入")
    async def tennis_ingest(self, event: AstrMessageEvent):
        """录入比赛截图"""
        await self._ensure_ready()
        if not event.get_group_id():
            yield event.plain_result("请在群聊中使用该命令。")
            return

        try:
            image_path = await self._message_parser.extract_first_image_path(event)
            preview = await self._ingest_service.ingest(
                match_type=MATCH_TYPE_SINGLES,
                platform=event.get_platform_name(),
                external_group_id=str(event.get_group_id()),
                group_name="",
                platform_user_id=str(event.get_sender_id()),
                submitted_by_name=event.get_sender_name(),
                unified_msg_origin=event.unified_msg_origin,
                source_image_path=image_path,
            )
        except MessageParserError as exc:
            yield event.plain_result(ResultRenderer.ingest_error_text(str(exc)))
            return
        except FileNotFoundError as exc:
            yield event.plain_result(ResultRenderer.ingest_error_text(str(exc)))
            return
        except ExtractionError as exc:
            yield event.plain_result(ResultRenderer.ingest_error_text(str(exc)))
            return
        except ValueError as exc:
            yield event.plain_result(ResultRenderer.ingest_error_text(str(exc)))
            return

        yield event.plain_result(ResultRenderer.ingest_preview_text(preview))

    @tennis.command("双打录入")
    async def tennis_doubles_ingest(self, event: AstrMessageEvent):
        """录入双打比赛截图"""
        await self._ensure_ready()
        if not event.get_group_id():
            yield event.plain_result("请在群聊中使用该命令。")
            return

        try:
            image_path = await self._message_parser.extract_first_image_path(event)
            preview = await self._ingest_service.ingest(
                match_type=MATCH_TYPE_DOUBLES,
                platform=event.get_platform_name(),
                external_group_id=str(event.get_group_id()),
                group_name="",
                platform_user_id=str(event.get_sender_id()),
                submitted_by_name=event.get_sender_name(),
                unified_msg_origin=event.unified_msg_origin,
                source_image_path=image_path,
            )
        except MessageParserError as exc:
            yield event.plain_result(ResultRenderer.ingest_error_text(str(exc)))
            return
        except FileNotFoundError as exc:
            yield event.plain_result(ResultRenderer.ingest_error_text(str(exc)))
            return
        except ExtractionError as exc:
            yield event.plain_result(ResultRenderer.ingest_error_text(str(exc)))
            return
        except ValueError as exc:
            yield event.plain_result(ResultRenderer.ingest_error_text(str(exc)))
            return

        yield event.plain_result(ResultRenderer.ingest_preview_text(preview))

    @tennis.command("确认")
    async def tennis_confirm(self, event: AstrMessageEvent, match_code: str):
        """确认待入库记录"""
        await self._ensure_ready()
        if not event.get_group_id():
            yield event.plain_result("请在群聊中使用该命令。")
            return

        try:
            result = await self._confirmation_service.confirm(
                platform=event.get_platform_name(),
                external_group_id=str(event.get_group_id()),
                operator_user_id=str(event.get_sender_id()),
                match_code=match_code,
            )
        except ConfirmationError as exc:
            yield event.plain_result(ResultRenderer.confirmation_error_text(str(exc)))
            return

        yield event.plain_result(
            ResultRenderer.confirmation_success_text(result.message)
        )

    @tennis.command("取消")
    async def tennis_cancel(self, event: AstrMessageEvent, match_code: str):
        """取消待入库记录"""
        await self._ensure_ready()
        if not event.get_group_id():
            yield event.plain_result("请在群聊中使用该命令。")
            return

        try:
            result = await self._confirmation_service.cancel(
                platform=event.get_platform_name(),
                external_group_id=str(event.get_group_id()),
                operator_user_id=str(event.get_sender_id()),
                match_code=match_code,
            )
        except ConfirmationError as exc:
            yield event.plain_result(ResultRenderer.confirmation_error_text(str(exc)))
            return

        yield event.plain_result(
            ResultRenderer.confirmation_success_text(result.message)
        )

    @tennis.command("删除")
    async def tennis_delete(self, event: AstrMessageEvent, match_code: str):
        """删除记录"""
        await self._ensure_ready()
        if not event.get_group_id():
            yield event.plain_result("请在群聊中使用该命令。")
            return

        try:
            result = await self._delete_service.delete_match(
                platform=event.get_platform_name(),
                external_group_id=str(event.get_group_id()),
                operator_user_id=str(event.get_sender_id()),
                is_admin=event.is_admin(),
                match_code=match_code,
            )
        except DeleteError as exc:
            yield event.plain_result(ResultRenderer.delete_error_text(str(exc)))
            return

        yield event.plain_result(ResultRenderer.delete_success_text(result.message))

    @tennis.command("战绩")
    async def tennis_stats(self, event: AstrMessageEvent, game_nickname: str = ""):
        """查看个人战绩"""
        await self._ensure_ready()
        if not event.get_group_id():
            yield event.plain_result("请在群聊中使用该命令。")
            return
        if not game_nickname.strip():
            yield event.plain_result("请使用 `/网球 战绩 <游戏昵称>` 查询。")
            return
        try:
            summary = await self._query_service.get_player_stats(
                platform=event.get_platform_name(),
                external_group_id=str(event.get_group_id()),
                game_nickname=game_nickname,
            )
        except QueryError as exc:
            yield event.plain_result(ResultRenderer.query_error_text(str(exc)))
            return
        yield event.plain_result(ResultRenderer.player_stats_text(summary))

    @tennis.command("最近")
    async def tennis_recent(
        self,
        event: AstrMessageEvent,
        game_nickname: str = "",
        count: int = 5,
    ):
        """查看最近比赛"""
        await self._ensure_ready()
        if not event.get_group_id():
            yield event.plain_result("请在群聊中使用该命令。")
            return
        if not game_nickname.strip():
            yield event.plain_result("请使用 `/网球 最近 <游戏昵称> [条数]` 查询。")
            return
        safe_count = min(max(count, 1), 10)
        try:
            items = await self._query_service.get_recent_matches(
                platform=event.get_platform_name(),
                external_group_id=str(event.get_group_id()),
                game_nickname=game_nickname,
                limit=safe_count,
            )
        except QueryError as exc:
            yield event.plain_result(ResultRenderer.query_error_text(str(exc)))
            return
        yield event.plain_result(ResultRenderer.recent_matches_text(items))

    @tennis.command("排行")
    async def tennis_ranking(self, event: AstrMessageEvent, metric: str = "胜场", top_n: int = 10):
        """查看群排行"""
        await self._ensure_ready()
        if not event.get_group_id():
            yield event.plain_result("请在群聊中使用该命令。")
            return
        safe_top_n = min(max(top_n, 1), 20)
        try:
            metric_key, entries = await self._ranking_service.get_ranking(
                platform=event.get_platform_name(),
                external_group_id=str(event.get_group_id()),
                metric=metric,
                top_n=safe_top_n,
            )
        except RankingError as exc:
            yield event.plain_result(ResultRenderer.query_error_text(str(exc)))
            return
        yield event.plain_result(ResultRenderer.ranking_text(metric_key, entries))

    async def terminate(self):
        if self._terminating:
            return
        self._terminating = True
        await self._db.close()
