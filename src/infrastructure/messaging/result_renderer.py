from collections.abc import Sequence

from ...application.dto.ingest import IngestPreview
from ...application.dto.query import PlayerStatsSummary, RecentMatchItem
from ...application.dto.ranking import RankingEntry


class ResultRenderer:
    @staticmethod
    def help_text() -> str:
        return "\n".join(
            [
                "网球插件当前可用命令：",
                "/网球 帮助",
                "/网球 录入",
                "/网球 取消 <记录号>",
                "/网球 删除 <记录号>",
                "/网球 战绩 <游戏昵称>",
                "/网球 最近 <游戏昵称> [条数]",
                "/网球 排行 [指标] [人数]",
                "",
                "默认完整记录会直接入库，发现有误可再取消。",
                "当前版本无需绑定昵称，查询时直接指定游戏内昵称。",
                "排行指标支持：胜场、胜率、场次、得分、胜球",
            ]
        )

    @staticmethod
    def ingest_preview_text(preview: IngestPreview) -> str:
        lines = [
            "网球记录预览",
            f"记录号: {preview.match_code}",
            f"状态: {preview.status}",
        ]
        for player in preview.players:
            display_name = player.raw_name
            if player.resolved and player.resolved_display_name:
                display_name = f"{player.raw_name} ({player.resolved_display_name})"
            lines.append(
                f"玩家{player.side}: {display_name} | 点数 {player.points_won if player.points_won is not None else '?'}"
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
            f"累计得分: {summary.total_points_won}",
            f"累计胜球: {summary.total_winners}",
            f"累计发球得分: {summary.total_serve_points_won}",
            f"累计失误: {summary.total_errors}",
            f"累计双误: {summary.total_double_faults}",
        ]
        if summary.average_net_play_rate is not None:
            lines.append(f"平均网前截击率: {summary.average_net_play_rate * 100:.1f}%")
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
    def ranking_text(metric_key: str, entries: Sequence[RankingEntry]) -> str:
        metric_name = {
            "wins": "胜场",
            "win_rate": "胜率",
            "matches": "场次",
            "points": "得分",
            "winners": "胜球",
        }.get(metric_key, metric_key)
        lines = [f"群排行 - {metric_name}"]
        for entry in entries:
            if metric_key == "win_rate":
                value_str = f"{entry.value * 100:.1f}%"
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
