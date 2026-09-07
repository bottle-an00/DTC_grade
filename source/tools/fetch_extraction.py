import argparse
import concurrent.futures
import json
import urllib.request

from tools.graph_auth import get_access_token
from tools.notify_teams import send_teams_message
from tools.resolve_workbook import resolve_workbook_id


def fetch_extraction(webhook_url: str, workbook_id: str, timeout: float, offset: int = 0, limit: int = 1000) -> dict:
    """POST to the n8n DTC Excel Extraction webhook for one page of sheets
    (offset/limit) and return its parsed JSON response:
    {"rows": [...], "suggestions": [...], "totalSheets": N} (suggestions is
    only present when some sheets in this page weren't in the mapping
    table).

    workbook_id is the target Excel file's Graph driveItem id -- the
    workflow reads whichever file this points to (n8n's Workbook field has
    no "By URL" mode here, only "By ID", so the caller must resolve a share
    link to an id first -- see tools.resolve_workbook).
    """
    payload = json.dumps({"workbook_id": workbook_id, "offset": offset, "limit": limit}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.status
        raw = response.read()

    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        preview = raw[:200].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"n8n 웹훅 응답이 올바른 JSON이 아닙니다 (status={status}, body={preview!r}). "
            "테스트 웹훅(webhook-test)은 호출당 1회만 응답하므로, 여러 번 반복 호출되는 이 파이프라인에는 "
            "워크플로우를 Active로 켠 뒤 프로덕션 웹훅 URL(webhook-test가 아닌 webhook)을 사용해야 합니다."
        ) from exc


def fetch_all_extraction(
    webhook_url: str, workbook_id: str, timeout: float, chunk_size: int = 15, max_concurrency: int = 5
) -> dict:
    """Page through all sheets in chunk_size-sized webhook calls and merge
    the results. Chunking alone only dodges n8n's gateway timeout (a single
    huge call can trip a 502) -- it doesn't make the underlying sheet-by-sheet
    Excel API work inside n8n any faster, so calling chunks one after another
    is just as slow in total as one big call. Firing up to max_concurrency
    chunk requests at once lets n8n process several chunks in parallel
    instead, cutting real wall-clock time roughly by that factor.
    """
    first = fetch_extraction(webhook_url, workbook_id, timeout, offset=0, limit=chunk_size)
    total_sheets = first.get("totalSheets", chunk_size)

    remaining_offsets = list(range(chunk_size, total_sheets, chunk_size))
    pages = [first]

    if remaining_offsets:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            futures = {
                executor.submit(fetch_extraction, webhook_url, workbook_id, timeout, offset, chunk_size): offset
                for offset in remaining_offsets
            }
            results_by_offset = {futures[future]: future.result() for future in concurrent.futures.as_completed(futures)}
        pages.extend(results_by_offset[offset] for offset in remaining_offsets)

    rows: list[dict] = []
    suggestions: list[dict] = []
    for page in pages:
        rows.extend(page.get("rows", []))
        suggestions.extend(page.get("suggestions", []))

    merged = {"rows": rows}
    if suggestions:
        merged["suggestions"] = suggestions
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch the matched DTC JSON from the n8n Excel extraction webhook and notify Teams"
    )
    parser.add_argument("--webhook-url", required=True, help="n8n Cloud Webhook URL for the extraction workflow")
    parser.add_argument("--workbook-url", required=True, help="OneDrive share link of the master Excel file to read")
    parser.add_argument("--output-json", required=True, help="Path to write the matched JSON (rows)")
    parser.add_argument("--teams-webhook-url", required=True, help="Teams Incoming Webhook URL")
    parser.add_argument("--webhook-timeout", type=float, default=300.0)
    parser.add_argument("--chunk-size", type=int, default=15, help="Sheets per webhook call, to avoid gateway timeouts")
    parser.add_argument(
        "--max-concurrency", type=int, default=5, help="How many chunk requests to run at once, to speed up large workbooks"
    )
    args = parser.parse_args()

    try:
        workbook_id = resolve_workbook_id(args.workbook_url, get_access_token())
        result = fetch_all_extraction(
            args.webhook_url, workbook_id, args.webhook_timeout, args.chunk_size, args.max_concurrency
        )
        rows = result.get("rows", [])

        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump({"rows": rows}, f, ensure_ascii=False)

        send_teams_message(
            args.teams_webhook_url,
            "DTC 매칭 JSON 준비 완료",
            f"파일: {args.output_json}\n행 수: {len(rows)}건",
        )

        suggestions = result.get("suggestions")
        if suggestions:
            lines = "\n".join(
                f"- {s['sheet']} -> AI 추천: {s['suggested_system']} ({s['reasoning']})" for s in suggestions
            )
            send_teams_message(
                args.teams_webhook_url,
                "DTC 매핑 필요 - 새 시트 발견, AI 추천 포함",
                "다음 시트가 매핑 테이블에 없어 AI가 자동으로 추천했습니다. 확인 후 "
                "config/sheet_system_mapping.json과 n8n의 'Attach System' 노드에 반영해주세요:\n\n" + lines,
            )
    except Exception as exc:
        send_teams_message(args.teams_webhook_url, "DTC 매칭 JSON 가져오기 실패", f"오류: {exc}")
        raise


if __name__ == "__main__":
    main()
