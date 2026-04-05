import json
import re
from dataclasses import dataclass

from ..config.config_manager import ConfigManager


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
        unified_msg_origin: str,
        image_path: str,
    ) -> ExtractionResult:
        provider_id = self._config_manager.get_provider_id()
        if not provider_id:
            provider_id = await self._context.get_current_chat_provider_id(
                unified_msg_origin
            )
        if not provider_id:
            raise ExtractionError("未找到可用的多模态模型 Provider。")

        prompt = self._build_user_prompt()
        try:
            llm_resp = await self._context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                image_urls=[image_path],
                system_prompt=self._config_manager.get_extraction_system_prompt(),
                temperature=0,
            )
        except Exception as exc:
            raise ExtractionError(f"调用多模态模型失败: {exc}") from exc
        raw_text = llm_resp.completion_text.strip()
        payload = self._extract_json_payload(raw_text)
        normalized = self._normalize_payload(payload)
        return ExtractionResult(
            raw_text=raw_text,
            normalized_payload=normalized,
            missing_fields=normalized["missing_fields"],
        )

    def _build_user_prompt(self) -> str:
        return "\n".join(
            [
                self._config_manager.get_extraction_user_prompt_template(),
                "",
                "请严格输出 JSON 对象，字段如下：",
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
                '  "winner_side": 1,',
                '  "missing_fields": [],',
                '  "is_complete": true',
                "}",
                "如果原图里字段缺失，请把缺失字段写进 missing_fields，且不要编造数据。",
            ]
        )

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

    def _normalize_payload(self, payload: dict) -> dict:
        players = payload.get("players")
        if not isinstance(players, list) or len(players) != 2:
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
            normalized_players.append(
                {
                    "side": self._as_int(player.get("side"), default=index),
                    "name": name,
                    "points_won": self._as_int(player.get("points_won")),
                    "winners": self._as_int(player.get("winners")),
                    "serve_points_won": self._as_int(player.get("serve_points_won")),
                    "errors": self._as_int(player.get("errors")),
                    "double_faults": self._as_int(player.get("double_faults")),
                    "net_play_rate": self._as_rate(player.get("net_play_rate")),
                }
            )

        winner_side = self._as_int(payload.get("winner_side"))
        if winner_side not in {1, 2}:
            winner_side = self._derive_winner_side(normalized_players)
        if winner_side not in {1, 2}:
            missing_fields.append("winner_side")

        normalized = {
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

    def _derive_winner_side(self, players: list[dict]) -> int | None:
        player1 = players[0]
        player2 = players[1]
        if player1.get("points_won") is None or player2.get("points_won") is None:
            return None
        if player1["points_won"] == player2["points_won"]:
            return None
        return 1 if player1["points_won"] > player2["points_won"] else 2

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
