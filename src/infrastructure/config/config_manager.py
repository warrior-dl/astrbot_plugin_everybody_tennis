from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot.api import AstrBotConfig


class ConfigManager:
    def __init__(self, config: "AstrBotConfig | dict[str, Any]"):
        self._config = config

    def _group(self, name: str) -> dict:
        return self._config.get(name, {})

    def is_enabled(self) -> bool:
        return self._group("basic").get("enabled", True)

    def is_group_only(self) -> bool:
        return self._group("basic").get("group_only", True)

    def allow_submitter_delete(self) -> bool:
        return self._group("basic").get("allow_submitter_delete", True)

    def get_provider_id(self) -> str:
        return self._group("llm").get("provider_id", "")

    def get_pending_expire_hours(self) -> int:
        return self._group("storage").get("pending_expire_hours", 24)

    def get_min_matches_for_win_rate(self) -> int:
        return self._group("ranking").get("min_matches_for_win_rate", 3)

    def get_default_top_n(self) -> int:
        return self._group("ranking").get("default_top_n", 10)

    def get_extraction_system_prompt(self) -> str:
        return self._group("prompts").get(
            "extraction_system_prompt",
            "你是一个网球比赛数据提取助手。请严格输出 JSON。",
        )

    def get_extraction_user_prompt_template(self) -> str:
        return self._group("prompts").get(
            "extraction_user_prompt_template",
            "请从截图中提取网球比赛统计信息。",
        )
