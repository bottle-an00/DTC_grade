import argparse
import csv
import json
import os
import urllib.request

from dtc_transform.models import RawRow
from dtc_transform.reconstruct import reconstruct_rows
from tools.apply_ai_suggestions import merge_ai_suggestions
from tools.derive_mapping import _load_reference_rows, derive_mapping, low_confidence_rows
from tools.notify_teams import send_teams_message
from tools.review_context import build_review_context


def call_ai_review_webhook(webhook_url: str, review_context: list[dict], timeout: float) -> list[dict]:
    """POST the review context to an n8n Webhook and return its parsed JSON
    response: a list of {"sheet", "suggested_system", "reasoning"} entries.

    n8n handles the AI Agent call and responds synchronously via a
    "Respond to Webhook" node -- this is the bridge that lets a locally-run
    Python driver use n8n Cloud's AI Agent without needing Execute Command
    (unavailable on Cloud) anywhere in the loop.
    """
    payload = json.dumps({"sheets": review_context}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run_ai_review(
    raw_rows: list[RawRow],
    reference_rows: list[tuple[str, str, str]],
    existing_mapping: dict[str, dict] | None,
    call_webhook,
    confidence_threshold: float = 0.5,
    top_n_candidates: int = 5,
    sample_size: int = 8,
) -> dict:
    """Regenerate the sheet mapping and, for any sheets still below the
    confidence threshold, ask an AI reviewer (via call_webhook) for a
    suggestion. call_webhook is injected so this stays testable without a
    real network call: call_webhook(review_context) -> list of
    {"sheet", "suggested_system", "reasoning"}.

    Sheets with no open review item (nothing below threshold) never trigger
    call_webhook at all.
    """
    mapping = derive_mapping(raw_rows, reference_rows, existing=existing_mapping)
    review_rows = low_confidence_rows(mapping, confidence_threshold)

    if not review_rows:
        return {"mapping": mapping, "review_rows": review_rows, "ai_suggestions": []}

    review_sheets = [row["sheet"] for row in review_rows]
    context = build_review_context(
        raw_rows,
        reference_rows,
        review_sheets,
        top_n_candidates=top_n_candidates,
        sample_size=sample_size,
    )
    ai_suggestions = call_webhook(context)
    annotated_rows = merge_ai_suggestions(review_rows, ai_suggestions)

    return {"mapping": mapping, "review_rows": annotated_rows, "ai_suggestions": ai_suggestions}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate the DTC sheet mapping, get AI review suggestions for "
            "low-confidence sheets via an n8n webhook, and notify Teams with the result"
        )
    )
    parser.add_argument("--raw-input", required=True, help="Path to the raw tab-separated export")
    parser.add_argument("--reference-db", required=True, help="Path to the existing dtc_master sqlite")
    parser.add_argument("--mapping", required=True, help="Path to config/sheet_system_mapping.json (read+write)")
    parser.add_argument("--review-csv", required=True, help="Path to write the AI-annotated review CSV")
    parser.add_argument("--n8n-webhook-url", required=True, help="n8n Cloud Webhook URL for the AI review workflow")
    parser.add_argument("--teams-webhook-url", required=True, help="Teams Incoming Webhook URL")
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    parser.add_argument("--top-n-candidates", type=int, default=5)
    parser.add_argument("--sample-size", type=int, default=8)
    parser.add_argument("--webhook-timeout", type=float, default=300.0)
    args = parser.parse_args()

    try:
        with open(args.raw_input, encoding="utf-8", errors="replace") as f:
            raw_rows, _orphans, _anomalous_field_count = reconstruct_rows(f.readlines())

        reference_rows = _load_reference_rows(args.reference_db)

        existing_mapping = None
        if os.path.exists(args.mapping):
            with open(args.mapping, encoding="utf-8") as f:
                existing_mapping = json.load(f)

        result = run_ai_review(
            raw_rows,
            reference_rows,
            existing_mapping,
            call_webhook=lambda context: call_ai_review_webhook(args.n8n_webhook_url, context, args.webhook_timeout),
            confidence_threshold=args.confidence_threshold,
            top_n_candidates=args.top_n_candidates,
            sample_size=args.sample_size,
        )

        with open(args.mapping, "w", encoding="utf-8") as f:
            json.dump(result["mapping"], f, ensure_ascii=False, indent=2, sort_keys=True)

        fieldnames = ["sheet", "system", "confidence", "hits", "ai_suggestion", "ai_reasoning"]
        with open(args.review_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in result["review_rows"]:
                writer.writerow({**{k: "" for k in fieldnames}, **row})

        review_count = len(result["review_rows"])
        send_teams_message(
            args.teams_webhook_url,
            "DTC 매핑 AI 검토 완료",
            f"검토된 시트 수: {review_count}건\n\n전체 결과: {args.review_csv} (ai_suggestion / ai_reasoning 컬럼 확인)",
        )
    except Exception as exc:
        send_teams_message(args.teams_webhook_url, "DTC 매핑 AI 검토 실패", f"오류: {exc}")
        raise


if __name__ == "__main__":
    main()
