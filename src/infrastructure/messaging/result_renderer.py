from collections.abc import Sequence

from ...application.dto.ingest import IngestPreview
from ...application.dto.query import DoublesRecentMatchItem, PlayerStatsSummary, RecentMatchItem
from ...application.dto.ranking import RankingEntry
from ...shared.match_types import MATCH_TYPE_DOUBLES, match_type_label


class ResultRenderer:
    @staticmethod
    def help_text() -> str:
        return "\n".join(
            [
                "网球插件当前可用命令：",
                "/网球 帮助",
                "/网球 录入",
                "/网球 双打录入",
                "/网球 确认 <记录号>",
                "/网球 取消 <记录号>",
                "/网球 删除 <记录号>",
                "/网球 战绩 <游戏昵称>",
                "/网球 最近 <游戏昵称> [条数]",
                "/网球 双打战绩 <游戏昵称>",
                "/网球 双打最近 <游戏昵称> [条数]",
                "/网球 排行 [指标] [人数]",
                "",
                "默认完整记录会直接入库，发现有误可再取消。",
                "当前版本无需绑定昵称，查询时直接指定游戏内昵称。",
                "双打当前支持录入、战绩查询和最近比赛查询。",
                "排行指标支持：胜场、胜率、场次、场均得分、场均胜球",
            ]
        )

    @staticmethod
    def ingest_preview_text(preview: IngestPreview) -> str:
        lines = [
            f"网球{match_type_label(preview.match_type)}记录预览",
            f"记录号: {preview.match_code}",
            f"状态: {preview.status}",
        ]
        if preview.match_type == MATCH_TYPE_DOUBLES:
            lines.extend(ResultRenderer._doubles_players_lines(preview))
        else:
            for player in preview.players:
                lines.append(
                    f"玩家{player.side}: {player.raw_name} | 点数 {player.points_won if player.points_won is not None else '?'}"
                )
        if preview.set_count is not None or preview.game_count is not None:
            lines.append(
                f"盘/局: {preview.set_count if preview.set_count is not None else '?'}盘 {preview.game_count if preview.game_count is not None else '?'}局"
            )
        if preview.duration_seconds is not None:
            lines.append(f"时长: {ResultRenderer._format_duration(preview.duration_seconds)}")
        if preview.max_rally_count is not None:
            lines.append(f"最长回合: {preview.max_rally_count}")
        lines.append(
            "缺失字段: "
            + ("无" if not preview.missing_fields else ", ".join(preview.missing_fields))
        )
        if preview.duplicate_hint:
            lines.append("提示: 该截图与历史记录疑似重复，请留意是否重复录入。")
        if preview.auto_confirmed:
            lines.extend(
                [
                    "结果: 记录已自动确认并入库。",
                    f"如需撤销，请发送 `/网球 取消 {preview.match_code}`",
                ]
            )
        elif preview.expires_at is not None:
            lines.append(
                f"待确认截止: {preview.expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
            lines.extend(
                [
                    "",
                    f"请发送 `/网球 确认 {preview.match_code}` 或 `/网球 取消 {preview.match_code}`",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _doubles_players_lines(preview: IngestPreview) -> list[str]:
        lines: list[str] = []
        for side in (1, 2):
            team_players = [player for player in preview.players if player.side == side]
            team_names = " / ".join(player.raw_name for player in team_players) or "未知"
            team_points = (
                sum(player.points_won for player in team_players if player.points_won is not None)
                if all(player.points_won is not None for player in team_players)
                else None
            )
            lines.append(
                f"队伍{side}: {team_names} | 总点数 {team_points if team_points is not None else '?'}"
            )
            for player in team_players:
                detail = [
                    f"玩家{player.player_slot}: {player.raw_name}",
                    f"点数 {player.points_won if player.points_won is not None else '?'}",
                ]
                if player.max_serve_speed_kmh is not None:
                    detail.append(f"最高球速 {player.max_serve_speed_kmh}km/h")
                lines.append("  - " + " | ".join(detail))
        return lines

    @staticmethod
    def ingest_error_text(message: str) -> str:
        return f"录入失败: {message}"

    @staticmethod
    def confirmation_success_text(message: str) -> str:
        return message

    @staticmethod
    def confirmation_error_text(message: str) -> str:
        return f"操作失败: {message}"

    @staticmethod
    def delete_success_text(message: str) -> str:
        return message

    @staticmethod
    def delete_error_text(message: str) -> str:
        return f"删除失败: {message}"

    @staticmethod
    def query_error_text(message: str) -> str:
        return f"查询失败: {message}"

    @staticmethod
    def player_stats_text(summary: PlayerStatsSummary) -> str:
        lines = [
            f"{summary.display_name} 的网球战绩",
            f"总场次: {summary.total_matches}",
            f"胜负: {summary.wins} 胜 / {summary.losses} 负",
            f"胜率: {summary.win_rate * 100:.1f}%",
            f"场均得分: {ResultRenderer._format_decimal(summary.average_points_won)}",
            f"场均胜球: {ResultRenderer._format_decimal(summary.average_winners)}",
            f"场均发球得分: {ResultRenderer._format_decimal(summary.average_serve_points_won)}",
            f"场均失误: {ResultRenderer._format_decimal(summary.average_errors)}",
            f"场均双误: {ResultRenderer._format_decimal(summary.average_double_faults)}",
        ]
        if summary.average_net_play_rate is not None:
            lines.append(f"平均网前截击率: {summary.average_net_play_rate * 100:.1f}%")
        return "\n".join(lines)

    @staticmethod
    def doubles_player_stats_text(summary: PlayerStatsSummary) -> str:
        lines = [
            f"{summary.display_name} 的双打战绩",
            f"总场次: {summary.total_matches}",
            f"胜负: {summary.wins} 胜 / {summary.losses} 负",
            f"胜率: {summary.win_rate * 100:.1f}%",
            f"场均得分: {ResultRenderer._format_decimal(summary.average_points_won)}",
            f"场均胜球: {ResultRenderer._format_decimal(summary.average_winners)}",
            f"场均发球得分: {ResultRenderer._format_decimal(summary.average_serve_points_won)}",
            f"场均失误: {ResultRenderer._format_decimal(summary.average_errors)}",
            f"场均双误: {ResultRenderer._format_decimal(summary.average_double_faults)}",
        ]
        if summary.average_net_play_rate is not None:
            lines.append(f"平均网前截击率: {summary.average_net_play_rate * 100:.1f}%")
        if summary.average_max_serve_speed_kmh is not None:
            lines.append(
                f"平均最高球速: {ResultRenderer._format_decimal(summary.average_max_serve_speed_kmh)}km/h"
            )
        return "\n".join(lines)

    @staticmethod
    def recent_matches_text(items: Sequence[RecentMatchItem]) -> str:
        lines = ["最近比赛："]
        for item in items:
            result = "胜" if item.is_winner else "负"
            score = (
                f"{item.points_won}:{item.opponent_points_won}"
                if item.points_won is not None and item.opponent_points_won is not None
                else "比分未知"
            )
            confirmed_at = (
                item.confirmed_at.strftime("%Y-%m-%d %H:%M")
                if item.confirmed_at is not None
                else "时间未知"
            )
            duration = (
                ResultRenderer._format_duration(item.duration_seconds)
                if item.duration_seconds is not None
                else "时长未知"
            )
            lines.append(
                f"- {item.match_code} | {result} | 对手 {item.opponent_name} | {score} | {duration} | {confirmed_at}"
            )
        return "\n".join(lines)

    @staticmethod
    def doubles_recent_matches_text(items: Sequence[DoublesRecentMatchItem]) -> str:
        lines = ["最近双打："]
        for item in items:
            result = "胜" if item.is_winner else "负"
            team_score = (
                f"{item.team_points_won}:{item.opponent_team_points_won}"
                if item.team_points_won is not None and item.opponent_team_points_won is not None
                else "比分未知"
            )
            player_points = item.player_points_won if item.player_points_won is not None else "?"
            confirmed_at = (
                item.confirmed_at.strftime("%Y-%m-%d %H:%M")
                if item.confirmed_at is not None
                else "时间未知"
            )
            duration = (
                ResultRenderer._format_duration(item.duration_seconds)
                if item.duration_seconds is not None
                else "时长未知"
            )
            lines.append(
                f"- {item.match_code} | {result} | 队友 {item.teammate_name} | "
                f"对手 {' / '.join(item.opponent_names)} | 队伍比分 {team_score} | "
                f"本人点数 {player_points} | {duration} | {confirmed_at}"
            )
        return "\n".join(lines)

    @staticmethod
    def ranking_text(metric_key: str, entries: Sequence[RankingEntry]) -> str:
        metric_name = {
            "wins": "胜场",
            "win_rate": "胜率",
            "matches": "场次",
            "avg_points": "场均得分",
            "avg_winners": "场均胜球",
        }.get(metric_key, metric_key)
        lines = [f"群排行 - {metric_name}"]
        for entry in entries:
            if metric_key == "win_rate":
                value_str = f"{entry.value * 100:.1f}%"
            elif metric_key in {"avg_points", "avg_winners"}:
                value_str = ResultRenderer._format_decimal(entry.value)
            else:
                value_str = str(int(entry.value))
            detail_parts = [f"{metric_name} {value_str}"]
            if metric_key != "wins":
                detail_parts.append(f"胜场 {entry.wins}")
            if metric_key != "matches":
                detail_parts.append(f"场次 {entry.matches}")
            lines.append(
                f"{entry.rank}. {entry.display_name} | " + " | ".join(detail_parts)
            )
        return "\n".join(lines)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remain = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{remain:02d}"

    @staticmethod
    def _format_decimal(value: float) -> str:
        text = f"{value:.2f}"
        text = text.rstrip("0").rstrip(".")
        return text if text else "0"
