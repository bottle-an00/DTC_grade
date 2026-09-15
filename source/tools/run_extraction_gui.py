import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from tools.config_store import DEFAULT_CONFIG_PATH, load_config, save_config
from tools.graph_auth import get_access_token
from tools.notify_teams import build_simple_adaptive_card, build_unmapped_sheets_adaptive_card, send_teams_adaptive_card
from tools.resolve_workbook import list_folder_files
from tools.run_extraction import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_CONCURRENCY,
    build_success_message,
    build_unmapped_alert_items,
)
from tools.run_extraction import run_with_id as run_extraction_pipeline
from tools.run_extraction_app import derive_output_paths


# Shown under the two numeric options when "도움말 표시" is checked. Kept as
# one string per rendered line so each gets its own Label -- the toggle then
# hides the whole set with grid_remove() instead of rebuilding text.
OPTION_HELP_LINES = (
    "· 분할 크기 : 한 번의 요청에서 처리할 시트 개수입니다. 너무 크면 시간 초과 또는 "
    "메모리 부족으로 처리가 중단될 수 있습니다. (권장 10~20)",
    "· 동시 요청 수 : 요청을 동시에 몇 개 보낼지 정합니다. 늘리면 빨라지지만, 미매핑 "
    "시트가 많을 경우 AI 추천 호출이 한도를 초과해 실패할 수 있습니다. (권장 3~10)",
)


def validate_inputs(webhook_url: str, teams_notify_webhook_url: str, workbook_id: str, output_sqlite: str) -> str | None:
    """Returns an error message if any required field is blank/unselected, else None."""
    if not (webhook_url and teams_notify_webhook_url and workbook_id and output_sqlite):
        return "모든 값을 입력하고, 파일과 저장 위치를 선택해주세요."
    return None


def parse_positive_int(value: str, default: int, label: str) -> int:
    """A blank field falls back to `default`; anything else must be a positive integer."""
    value = value.strip()
    if not value:
        return default
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{label}는 1 이상이어야 합니다.")
    return parsed


class ExtractionApp:
    def __init__(self, root: tk.Tk, config_path: str = DEFAULT_CONFIG_PATH):
        self.root = root
        self.config_path = config_path
        self.config = load_config(config_path)
        self._files: list[dict] = []

        root.title("DTC 등급 추출 도구")

        tk.Label(root, text="n8n 웹훅 URL").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.webhook_entry = tk.Entry(root, width=60)
        self.webhook_entry.insert(0, self.config.get("webhook_url", ""))
        self.webhook_entry.grid(row=0, column=1, padx=8, pady=4)

        tk.Label(root, text="Teams 웹훅 URL").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.teams_entry = tk.Entry(root, width=60)
        self.teams_entry.insert(0, self.config.get("teams_notify_webhook_url", ""))
        self.teams_entry.grid(row=1, column=1, padx=8, pady=4)

        tk.Label(root, text="OneDrive 폴더 링크").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.folder_entry = tk.Entry(root, width=60)
        self.folder_entry.insert(0, self.config.get("folder_url", ""))
        self.folder_entry.grid(row=2, column=1, padx=8, pady=4)
        tk.Button(root, text="파일 목록 불러오기", command=self.on_load_files).grid(row=2, column=2, padx=8)

        tk.Label(root, text="처리할 Excel 파일").grid(row=3, column=0, sticky="nw", padx=8, pady=4)
        self.file_listbox = tk.Listbox(root, height=6, width=60)
        self.file_listbox.grid(row=3, column=1, padx=8, pady=4, sticky="w")

        tk.Label(root, text="저장 위치").grid(row=4, column=0, sticky="w", padx=8, pady=4)
        self.output_var = tk.StringVar()
        tk.Entry(root, textvariable=self.output_var, width=45, state="readonly").grid(
            row=4, column=1, sticky="w", padx=8, pady=4
        )
        tk.Button(root, text="찾아보기...", command=self.choose_output).grid(row=4, column=2, padx=8)

        options = tk.LabelFrame(root, text="처리 옵션 (기본값 권장)", padx=8, pady=6)
        options.grid(row=5, column=0, columnspan=3, sticky="we", padx=8, pady=6)

        tk.Label(options, text="분할 크기").grid(row=0, column=0, sticky="w")
        self.chunk_entry = tk.Entry(options, width=8)
        self.chunk_entry.insert(0, str(self.config.get("chunk_size", DEFAULT_CHUNK_SIZE)))
        self.chunk_entry.grid(row=0, column=1, sticky="w", padx=(4, 24))

        tk.Label(options, text="동시 요청 수").grid(row=0, column=2, sticky="w")
        self.concurrency_entry = tk.Entry(options, width=8)
        self.concurrency_entry.insert(0, str(self.config.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)))
        self.concurrency_entry.grid(row=0, column=3, sticky="w", padx=(4, 24))

        self.help_var = tk.BooleanVar(value=bool(self.config.get("show_option_help", True)))
        tk.Checkbutton(options, text="도움말 표시", variable=self.help_var, command=self.toggle_help).grid(
            row=0, column=4, sticky="w"
        )

        # One Label per line instead of embedded newlines -- grid places them,
        # and toggle_help() can show or hide the whole set at once.
        self.help_labels = [
            tk.Label(options, text=line, fg="gray30", justify="left", wraplength=620, anchor="w")
            for line in OPTION_HELP_LINES
        ]
        self.toggle_help()

        self.run_button = tk.Button(root, text="실행", command=self.on_run)
        self.run_button.grid(row=6, column=1, pady=12)

        self.status_label = tk.Label(root, text="", fg="blue", justify="left", wraplength=500)
        self.status_label.grid(row=7, column=0, columnspan=3, padx=8, pady=4)

    def toggle_help(self) -> None:
        show = self.help_var.get()
        for offset, label in enumerate(self.help_labels):
            if show:
                label.grid(row=1 + offset, column=0, columnspan=5, sticky="w", pady=(4, 0))
            else:
                label.grid_remove()
        self.config["show_option_help"] = show
        save_config(self.config_path, self.config)

    def choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="결과 sqlite 파일 저장 위치",
            defaultextension=".sqlite",
            initialfile="dtc_master.sqlite",
            filetypes=[("SQLite DB", "*.sqlite")],
        )
        if path:
            self.output_var.set(path)

    def on_load_files(self) -> None:
        folder_url = self.folder_entry.get().strip()
        if not folder_url:
            messagebox.showerror("입력 필요", "OneDrive 폴더 링크를 입력해주세요.")
            return

        self.config["folder_url"] = folder_url
        save_config(self.config_path, self.config)

        self.status_label.config(text="파일 목록을 불러오는 중입니다...")
        threading.Thread(target=self._load_files, args=(folder_url,), daemon=True).start()

    def _load_files(self, folder_url: str) -> None:
        try:
            files = list_folder_files(folder_url, get_access_token())
        except Exception as exc:
            self.root.after(0, self._on_files_loaded, [], f"파일 목록을 불러오지 못했습니다: {exc}")
            return

        message = f"{len(files)}개의 Excel 파일을 찾았습니다." if files else "이 폴더에 .xlsx 파일이 없습니다."
        self.root.after(0, self._on_files_loaded, files, message)

    def _on_files_loaded(self, files: list[dict], message: str) -> None:
        self._files = files
        self.file_listbox.delete(0, tk.END)
        for file in files:
            self.file_listbox.insert(tk.END, file["name"])
        self.status_label.config(text=message)

    def on_run(self) -> None:
        webhook_url = self.webhook_entry.get().strip()
        teams_notify_webhook_url = self.teams_entry.get().strip()
        output_sqlite = self.output_var.get().strip()

        selection = self.file_listbox.curselection()
        workbook_id = self._files[selection[0]]["id"] if selection else ""

        error = validate_inputs(webhook_url, teams_notify_webhook_url, workbook_id, output_sqlite)
        if error:
            messagebox.showerror("입력 필요", error)
            return

        try:
            chunk_size = parse_positive_int(self.chunk_entry.get(), DEFAULT_CHUNK_SIZE, "분할 크기")
            max_concurrency = parse_positive_int(
                self.concurrency_entry.get(), DEFAULT_MAX_CONCURRENCY, "동시 요청 수"
            )
        except ValueError as exc:
            messagebox.showerror("입력 오류", f"{exc}" if str(exc) else "1 이상의 정수로 입력해주세요.")
            return

        self.config["webhook_url"] = webhook_url
        self.config["teams_notify_webhook_url"] = teams_notify_webhook_url
        self.config["chunk_size"] = chunk_size
        self.config["max_concurrency"] = max_concurrency
        save_config(self.config_path, self.config)

        self.run_button.config(state="disabled")
        self.status_label.config(text="처리 중입니다...")

        threading.Thread(
            target=self._run_pipeline,
            args=(webhook_url, teams_notify_webhook_url, workbook_id, output_sqlite, chunk_size, max_concurrency),
            daemon=True,
        ).start()

    def _notify(self, teams_notify_webhook_url: str, title: str, text: str) -> None:
        send_teams_adaptive_card(teams_notify_webhook_url, build_simple_adaptive_card(title, text))

    def _run_pipeline(
        self,
        webhook_url: str,
        teams_notify_webhook_url: str,
        workbook_id: str,
        output_sqlite: str,
        chunk_size: int,
        max_concurrency: int,
    ) -> None:
        output_json, report_path = derive_output_paths(output_sqlite)
        try:
            result, stats = run_extraction_pipeline(
                webhook_url,
                workbook_id,
                output_json,
                output_sqlite,
                report_path,
                timeout=300.0,
                chunk_size=chunk_size,
                max_concurrency=max_concurrency,
            )
        except Exception as exc:
            self._notify(teams_notify_webhook_url, "DTC 등급 파이프라인 실패", f"오류: {exc}")
            self.root.after(0, self._on_done, f"실패: {exc}")
            return

        if stats["unmapped_sheets"]:
            title = "DTC 등급 파이프라인 - 매핑 필요"
            card = build_unmapped_sheets_adaptive_card(
                title,
                "다음 시트가 System에 매핑되지 않아 sqlite를 배포하지 않았습니다. 확인 후 체크해주세요:",
                build_unmapped_alert_items(stats, result),
            )
            send_teams_adaptive_card(teams_notify_webhook_url, card)
            self.root.after(0, self._on_done, f"매핑이 필요한 시트가 있습니다: {stats['unmapped_sheets']}")
        else:
            self._notify(
                teams_notify_webhook_url,
                "DTC 등급 sqlite 준비 완료",
                build_success_message(output_sqlite, report_path, stats),
            )
            self.root.after(0, self._on_done, f"완료: {output_sqlite} ({stats['after_expand_count']}건)")

    def _on_done(self, message: str) -> None:
        self.status_label.config(text=message)
        self.run_button.config(state="normal")


def main() -> None:
    root = tk.Tk()
    ExtractionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
