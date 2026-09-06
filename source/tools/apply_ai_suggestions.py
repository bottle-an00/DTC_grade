import argparse
import csv
import json


def merge_ai_suggestions(review_rows: list[dict], ai_suggestions: list[dict]) -> list[dict]:
    """Add ai_suggestion/ai_reasoning columns to each review row.

    `review_rows` are dicts read from the low-confidence review CSV.
    `ai_suggestions` are dicts like {"sheet", "suggested_system", "reasoning"}
    produced by the n8n AI Agent step. A sheet with no AI suggestion gets
    empty strings, never omitted -- the review CSV's row set is unchanged,
    only annotated. This never touches config/sheet_system_mapping.json;
    a human still applies any accepted suggestion manually.
    """
    suggestion_by_sheet = {item["sheet"]: item for item in ai_suggestions}

    merged = []
    for row in review_rows:
        suggestion = suggestion_by_sheet.get(row["sheet"])
        new_row = dict(row)
        new_row["ai_suggestion"] = suggestion["suggested_system"] if suggestion else ""
        new_row["ai_reasoning"] = suggestion["reasoning"] if suggestion else ""
        merged.append(new_row)

    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge AI-suggested mapping corrections into the review CSV")
    parser.add_argument("--review-csv", required=True, help="Path to the existing low-confidence sheets CSV")
    parser.add_argument("--ai-suggestions", required=True, help="Path to the AI Agent's suggestions JSON")
    parser.add_argument("--output", required=True, help="Path to write the annotated CSV")
    args = parser.parse_args()

    with open(args.review_csv, encoding="utf-8", newline="") as f:
        review_rows = list(csv.DictReader(f))

    with open(args.ai_suggestions, encoding="utf-8") as f:
        ai_suggestions = json.load(f)

    merged = merge_ai_suggestions(review_rows, ai_suggestions)

    fieldnames = list(review_rows[0].keys()) + ["ai_suggestion", "ai_reasoning"] if review_rows else [
        "sheet", "system", "confidence", "hits", "ai_suggestion", "ai_reasoning"
    ]

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged)


if __name__ == "__main__":
    main()
