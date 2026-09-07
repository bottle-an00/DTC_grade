import os
import sys

from tools.config_store import DEFAULT_CONFIG_PATH, load_config, save_config
from tools.notify_teams import send_teams_message
from tools.run_extraction import build_success_message, build_unmapped_alert_message
from tools.run_extraction import run as run_extraction_pipeline


def resolve_config(config: dict, prompt) -> dict:
    """Fill in webhook_url/teams_webhook_url via prompt(text) -> str only
    when missing, so a saved config is never asked for twice."""
    if not config.get("webhook_url"):
        config["webhook_url"] = prompt("n8n 웹훅 URL: ").strip()
    if not config.get("teams_webhook_url"):
        config["teams_webhook_url"] = prompt("Teams 웹훅 URL: ").strip()
    return config


def derive_output_paths(output_sqlite: str) -> tuple[str, str]:
    base, _ = os.path.splitext(output_sqlite)
    return base + "_extraction.json", base + "_report.txt"


def choose_output_sqlite_path(default_name: str = "dtc_master.sqlite") -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        return filedialog.asksaveasfilename(
            title="결과 sqlite 파일 저장 위치",
            defaultextension=".sqlite",
            initialfile=default_name,
            filetypes=[("SQLite DB", "*.sqlite")],
        )
    finally:
        root.destroy()


def main(config_path: str = DEFAULT_CONFIG_PATH) -> None:
    config = load_config(config_path)
    resolve_config(config, input)
    save_config(config_path, config)

    workbook_url = input("새 Excel 파일의 OneDrive 공유 링크: ").strip()

    output_sqlite = choose_output_sqlite_path()
    if not output_sqlite:
        print("저장 위치를 선택하지 않아 취소되었습니다.")
        input("Enter를 눌러 종료...")
        return

    output_json, report_path = derive_output_paths(output_sqlite)

    try:
        result, stats = run_extraction_pipeline(
            config["webhook_url"], workbook_url, output_json, output_sqlite, report_path, timeout=300.0
        )
    except Exception as exc:
        send_teams_message(config["teams_webhook_url"], "DTC 등급 파이프라인 실패", f"오류: {exc}")
        print(f"실패: {exc}")
        input("Enter를 눌러 종료...")
        sys.exit(1)

    if stats["unmapped_sheets"]:
        send_teams_message(
            config["teams_webhook_url"],
            "DTC 등급 파이프라인 - 매핑 필요",
            build_unmapped_alert_message(stats, result),
        )
        print("매핑이 필요한 시트가 있습니다:", stats["unmapped_sheets"])
    else:
        send_teams_message(
            config["teams_webhook_url"],
            "DTC 등급 sqlite 준비 완료",
            build_success_message(output_sqlite, report_path, stats),
        )
        print(f"완료: {output_sqlite} ({stats['after_expand_count']}건)")

    input("Enter를 눌러 종료...")


if __name__ == "__main__":
    main()
