import json
import re
from dataclasses import dataclass

from ..config.config_manager import ConfigManager
from ...shared.match_types import MATCH_TYPE_DOUBLES, MATCH_TYPE_SINGLES


class ExtractionError(Exception):
    pass


@dataclass(slots=True)
class ExtractionResult:
    raw_text: str
    normalized_payload: dict
    missing_fields: list[str]


class MultimodalExtractor:
    def __init__(self, context, config_manager: ConfigManager):
        self._context = context
        self._config_manager = config_manager

    async def extract(
        self,
        *,
        match_type: str,
        unified_msg_origin: str,
        image_path: str,
    ) -> ExtractionResult:
        configured_provider_id = self._config_manager.get_provider_id().strip()
        provider_id = configured_provider_id
        if not provider_id:
            provider_id = await self._context.get_current_chat_provider_id(
                unified_msg_origin
            )
        if not provider_id:
            raise ExtractionError(
                "未找到可用的多模态模型 Provider。请先在插件配置 `llm.provider_id` 中选择一个支持图片输入的聊天模型。"
            )

        prompt = self._build_user_prompt(match_type)
        try:
            llm_resp = await self._context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                image_urls=[image_path],
                system_prompt=self._config_manager.get_extraction_system_prompt(),
                temperature=0,
            )
        except Exception as exc:
            raise ExtractionError(
                self._build_provider_error_message(
                    exc=exc,
                    provider_id=provider_id,
                    configured=bool(configured_provider_id),
                )
            ) from exc
        raw_text = llm_resp.completion_text.strip()
        payload = self._extract_json_payload(raw_text)
        normalized = self._normalize_payload(payload, match_type)
        return ExtractionResult(
            raw_text=raw_text,
            normalized_payload=normalized,
            missing_fields=normalized["missing_fields"],
        )

    def _build_provider_error_message(
        self,
        *,
        exc: Exception,
        provider_id: str,
        configured: bool,
    ) -> str:
        message = str(exc)
        lowered = message.lower()

        if "unknown variant `image_url`" in lowered or "expected `text`" in lowered:
            prefix = (
                f"插件当前配置的 Provider `{provider_id}` 不支持图片输入。"
                if configured
                else "当前未在插件中单独配置截图提取 Provider，且回退到会话 Provider 后发现其不支持图片输入。"
            )
            return (
                prefix
                + " 请在插件配置 `llm.provider_id` 中选择一个支持多模态看图的聊天模型后重试。"
            )

        if "429" in lowered or "余额不足" in message or "无可用资源包" in message:
            return (
                f"调用多模态模型失败，Provider `{provider_id}` 当前额度不足或请求受限。"
                " 请检查对应模型账号余额、资源包或限流配置。"
            )

        if not configured:
            return (
                f"调用多模态模型失败: {message}"
                "。当前未在插件中显式配置 `llm.provider_id`，建议改为手动选择一个支持图片输入的 Provider。"
            )

        return f"调用多模态模型失败: {message}"

    def _build_user_prompt(self, match_type: str) -> str:
        lines = [
            self._config_manager.get_extraction_user_prompt_template(),
            "",
            f"当前识别模式: {'双打' if match_type == MATCH_TYPE_DOUBLES else '单打'}。",
            "请严格输出 JSON 对象。",
        ]
        if match_type == MATCH_TYPE_DOUBLES:
            lines.extend(
                [
                    "players 必须输出 4 个对象，并按截图中的玩家顺序排列。",
                    "前两个玩家视为队伍1，后两个玩家视为队伍2。",
                    "{",
                    '  "players": [',
                    "    {",
                    '      "name": "string",',
                    '      "points_won": 0,',
                    '      "winners": 0,',
                    '      "serve_points_won": 0,',
                    '      "errors": 0,',
                    '      "double_faults": 0,',
                    '      "net_play_rate": 0.0,',
                    '      "max_serve_speed_kmh": 0',
                    "    }",
                    "  ],",
                    '  "set_count": 0,',
                    '  "game_count": 0,',
                    '  "duration_seconds": 0,',
                    '  "max_rally_count": 0,',
                    '  "missing_fields": [],',
                    '  "is_complete": true',
                    "}",
                    "不要输出 winner_side，系统会根据同队两人的 points_won 总和自动判定胜负。",
                ]
            )
        else:
            lines.extend(
                [
                    "players 必须输出 2 个对象。",
                    "{",
                    '  "players": [',
                    "    {",
                    '      "side": 1,',
                    '      "name": "string",',
                    '      "points_won": 0,',
                    '      "winners": 0,',
                    '      "serve_points_won": 0,',
                    '      "errors": 0,',
                    '      "double_faults": 0,',
                    '      "net_play_rate": 0.0',
                    "    }",
                    "  ],",
                    '  "set_count": 0,',
                    '  "game_count": 0,',
                    '  "duration_seconds": 0,',
                    '  "max_rally_count": 0,',
                    '  "missing_fields": [],',
                    '  "is_complete": true',
                    "}",
                    "不要输出 winner_side，系统会根据双方 points_won 自动判定胜负。",
                ]
            )
        lines.append("如果原图里字段缺失，请把缺失字段写进 missing_fields，且不要编造数据。")
        return "\n".join(lines)

    def _extract_json_payload(self, text: str) -> dict:
        stripped = text.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        fenced_match = re.search(r"```json\s*(\{.*\})\s*```", stripped, re.S)
        if fenced_match:
            return json.loads(fenced_match.group(1))

        object_match = re.search(r"(\{.*\})", stripped, re.S)
        if object_match:
            return json.loads(object_match.group(1))

        raise ExtractionError("模型输出不是可解析的 JSON。")

    def _normalize_payload(self, payload: dict, match_type: str) -> dict:
        players = payload.get("players")
        expected_count = 4 if match_type == MATCH_TYPE_DOUBLES else 2
        if not isinstance(players, list) or len(players) != expected_count:
            raise ExtractionError("模型输出中的 players 字段无效。")

        normalized_players = []
        raw_missing_fields = payload.get("missing_fields") or []
        missing_fields = (
            [str(item) for item in raw_missing_fields]
            if isinstance(raw_missing_fields, list)
            else []
        )

        for index, player in enumerate(players, start=1):
            if not isinstance(player, dict):
                raise ExtractionError("模型输出中的玩家数据无效。")
            name = str(player.get("name", "")).strip()
            if not name:
                missing_fields.append(f"players[{index}].name")
            side = self._player_side(match_type=match_type, index=index, player=player)
            normalized_players.append(
                {
                    "side": side,
                    "player_slot": index,
                    "name": name,
                    "points_won": self._as_int(player.get("points_won")),
                    "winners": self._as_int(player.get("winners")),
                    "serve_points_won": self._as_int(player.get("serve_points_won")),
                    "errors": self._as_int(player.get("errors")),
                    "double_faults": self._as_int(player.get("double_faults")),
                    "net_play_rate": self._as_rate(player.get("net_play_rate")),
                    "max_serve_speed_kmh": self._as_int(player.get("max_serve_speed_kmh")),
                }
            )

        missing_fields = [
            field for field in missing_fields if str(field).strip() != "winner_side"
        ]

        winner_side = self._derive_winner_side(normalized_players, match_type)
        if winner_side not in {1, 2}:
            missing_fields.append("winner_side")

        normalized = {
            "match_type": match_type,
            "players": normalized_players,
            "set_count": self._as_int(payload.get("set_count")),
            "game_count": self._as_int(payload.get("game_count")),
            "duration_seconds": self._as_duration_seconds(payload.get("duration_seconds")),
            "max_rally_count": self._as_int(payload.get("max_rally_count")),
            "winner_side": winner_side,
            "missing_fields": sorted(set(missing_fields)),
            "is_complete": not missing_fields,
        }
        return normalized

    def _player_side(self, *, match_type: str, index: int, player: dict) -> int:
        if match_type == MATCH_TYPE_DOUBLES:
            return 1 if index <= 2 else 2
        return self._as_int(player.get("side"), default=index) or index

    def _derive_winner_side(self, players: list[dict], match_type: str) -> int | None:
        if match_type == MATCH_TYPE_DOUBLES:
            team1_points = self._team_points_total(players, side=1)
            team2_points = self._team_points_total(players, side=2)
            if team1_points is None or team2_points is None:
                return None
            if team1_points == team2_points:
                return None
            return 1 if team1_points > team2_points else 2

        player1 = players[0]
        player2 = players[1]
        if player1.get("points_won") is None or player2.get("points_won") is None:
            return None
        if player1["points_won"] == player2["points_won"]:
            return None
        return 1 if player1["points_won"] > player2["points_won"] else 2

    def _team_points_total(self, players: list[dict], *, side: int) -> int | None:
        team_players = [player for player in players if player.get("side") == side]
        if not team_players:
            return None
        if any(player.get("points_won") is None for player in team_players):
            return None
        return sum(player["points_won"] for player in team_players)

    def _as_int(self, value, default: int | None = None) -> int | None:
        if value in (None, ""):
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            digits = re.sub(r"[^\d-]", "", value)
            if digits:
                return int(digits)
        return default

    def _as_rate(self, value) -> float | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return value / 100 if value > 1 else float(value)
        if isinstance(value, str):
            stripped = value.strip()
            try:
                if stripped.endswith("%"):
                    stripped = stripped[:-1]
                    return float(stripped) / 100
                parsed = float(stripped)
                return parsed / 100 if parsed > 1 else parsed
            except ValueError:
                return None
        return None

    def _as_duration_seconds(self, value) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            stripped = value.strip()
            if re.fullmatch(r"\d{2}:\d{2}:\d{2}", stripped):
                hours, minutes, seconds = (int(part) for part in stripped.split(":"))
                return hours * 3600 + minutes * 60 + seconds
        return self._as_int(value)
