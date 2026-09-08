import argparse
import json

from tools.fetch_extraction import fetch_all_extraction
from tools.graph_auth import get_access_token
from tools.json_to_sqlite import convert
from tools.notify_teams import send_teams_chat_message, send_teams_message
from tools.resolve_workbook import resolve_workbook_id

DEFAULT_CHUNK_SIZE = 15
DEFAULT_MAX_CONCURRENCY = 5


def run_with_id(
    webhook_url: str,
    workbook_id: str,
    output_json: str,
    output_sqlite: str,
    report_path: str,
    timeout: float,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
) -> tuple[dict, dict]:
    """Same as run(), but for a caller that already has the file's Graph
    driveItem id (e.g. picked from tools.resolve_workbook.list_folder_files)
    and so has no share link left to resolve."""
    result = fetch_all_extraction(webhook_url, workbook_id, timeout, chunk_size, max_concurrency)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({"rows": result.get("rows", [])}, f, ensure_ascii=False)

    stats = convert(output_json, output_sqlite, report_path)
    return result, stats


def run(
    webhook_url: str,
    workbook_url: str,
    output_json: str,
    output_sqlite: str,
    report_path: str,
    timeout: float,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
) -> tuple[dict, dict]:
    workbook_id = resolve_workbook_id(workbook_url, get_access_token())
    return run_with_id(
        webhook_url, workbook_id, output_json, output_sqlite, report_path, timeout, chunk_size, max_concurrency
    )


def build_success_message(output_sqlite: str, report_path: str, stats: dict) -> str:
    return f"결과 파일: {output_sqlite}\n리포트: {report_path}\n행 수: {stats['after_expand_count']}건"


def build_unmapped_alert_message(stats: dict, result: dict) -> str:
    suggestions = {s["sheet"]: s for s in result.get("suggestions", [])}
    lines = []
    for sheet in stats["unmapped_sheets"]:
        suggestion = suggestions.get(sheet)
        if suggestion:
            lines.append(f"- {sheet} -> AI 추천: {suggestion['suggested_system']} ({suggestion['reasoning']})")
        else:
            lines.append(f"- {sheet}")

    return (
        "다음 시트가 System에 매핑되지 않아 sqlite를 배포하지 않았습니다. 확인 후 "
        "config/sheet_system_mapping.json과 n8n의 'Attach System' 노드에 반영해주세요:\n\n" + "\n".join(lines)
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch the matched DTC JSON from n8n, convert it to sqlite, and notify Teams with the result"
    )
    parser.add_argument("--webhook-url", required=True, help="n8n Cloud Webhook URL for the extraction workflow")
    parser.add_argument("--workbook-url", required=True, help="OneDrive share link of the master Excel file to read")
    parser.add_argument("--output-json", required=True, help="Path to write the matched JSON (rows)")
    parser.add_argument("--output", required=True, help="Path to write the output sqlite")
    parser.add_argument("--report", required=True, help="Path to write the run report")
    parser.add_argument("--teams-webhook-url", required=True, help="Teams Incoming Webhook URL")
    parser.add_argument(
        "--teams-chat-webhook-url",
        help="지정하면(--teams-chat-id와 함께) Incoming Webhook 채널 알림과 별도로, "
        "n8n의 'Notify Teams Chat' 워크플로우 웹훅을 통해 이 Teams 채팅(개인 채팅 포함)에도 알림",
    )
    parser.add_argument("--teams-chat-id", help="알림을 받을 Teams 채팅 ID (--teams-chat-webhook-url과 함께 지정)")
    parser.add_argument("--webhook-timeout", type=float, default=300.0)
    parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Sheets per webhook call, to avoid gateway timeouts"
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=DEFAULT_MAX_CONCURRENCY,
        help="How many chunk requests to run at once, to speed up large workbooks",
    )
    args = parser.parse_args()

    def notify(title: str, text: str) -> None:
        send_teams_message(args.teams_webhook_url, title, text)
        if args.teams_chat_webhook_url and args.teams_chat_id:
            send_teams_chat_message(args.teams_chat_webhook_url, args.teams_chat_id, title, text)

    try:
        result, stats = run(
            args.webhook_url,
            args.workbook_url,
            args.output_json,
            args.output,
            args.report,
            args.webhook_timeout,
            args.chunk_size,
            args.max_concurrency,
        )
    except Exception as exc:
        notify("DTC 등급 파이프라인 실패", f"오류: {exc}")
        raise

    if stats["unmapped_sheets"]:
        notify("DTC 등급 파이프라인 - 매핑 필요", build_unmapped_alert_message(stats, result))
        raise SystemExit(1)

    notify("DTC 등급 sqlite 준비 완료", build_success_message(args.output, args.report, stats))


if __name__ == "__main__":
    main()
