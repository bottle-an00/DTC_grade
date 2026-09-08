import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from tools.config_store import DEFAULT_CONFIG_PATH, load_config, save_config
from tools.graph_auth import get_access_token
from tools.notify_teams import send_teams_chat_message
from tools.resolve_workbook import list_folder_files
from tools.run_extraction import DEFAULT_MAX_CONCURRENCY, build_success_message, build_unmapped_alert_message
from tools.run_extraction import run_with_id as run_extraction_pipeline
from tools.run_extraction_app import derive_output_paths


def validate_inputs(
    webhook_url: str, teams_notify_webhook_url: str, teams_chat_id: str, workbook_id: str, output_sqlite: str
) -> str | None:
    """Returns an error message if any required field is blank/unselected, else None."""
    if not (webhook_url and teams_notify_webhook_url and teams_chat_id and workbook_id and output_sqlite):
        return "모든 값을 입력하고, 파일과 저장 위치를 선택해주세요."
    return None


def parse_max_concurrency(value: str) -> int:
    """A blank field falls back to DEFAULT_MAX_CONCURRENCY; anything else must be a positive integer."""
    value = value.strip()
    if not value:
        return DEFAULT_MAX_CONCURRENCY
    parsed = int(value)
    if parsed < 1:
        raise ValueError("동시 요청 수는 1 이상이어야 합니다.")
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

        tk.Label(root, text="Teams 채팅 ID").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.teams_chat_id_entry = tk.Entry(root, width=60)
        self.teams_chat_id_entry.insert(0, self.config.get("teams_chat_id", ""))
        self.teams_chat_id_entry.grid(row=2, column=1, padx=8, pady=4)

        tk.Label(root, text="OneDrive 폴더 링크").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self.folder_entry = tk.Entry(root, width=60)
        self.folder_entry.insert(0, self.config.get("folder_url", ""))
        self.folder_entry.grid(row=3, column=1, padx=8, pady=4)
        tk.Button(root, text="파일 목록 불러오기", command=self.on_load_files).grid(row=3, column=2, padx=8)

        tk.Label(root, text="처리할 Excel 파일").grid(row=4, column=0, sticky="nw", padx=8, pady=4)
        self.file_listbox = tk.Listbox(root, height=6, width=60)
        self.file_listbox.grid(row=4, column=1, padx=8, pady=4, sticky="w")

        tk.Label(root, text="저장 위치").grid(row=5, column=0, sticky="w", padx=8, pady=4)
        self.output_var = tk.StringVar()
        tk.Entry(root, textvariable=self.output_var, width=45, state="readonly").grid(
            row=5, column=1, sticky="w", padx=8, pady=4
        )
        tk.Button(root, text="찾아보기...", command=self.choose_output).grid(row=5, column=2, padx=8)

        tk.Label(root, text="동시 요청 수").grid(row=6, column=0, sticky="w", padx=8, pady=4)
        self.concurrency_entry = tk.Entry(root, width=10)
        self.concurrency_entry.insert(0, str(self.config.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)))
        self.concurrency_entry.grid(row=6, column=1, sticky="w", padx=8, pady=4)

        self.run_button = tk.Button(root, text="실행", command=self.on_run)
        self.run_button.grid(row=7, column=1, pady=12)

        self.status_label = tk.Label(root, text="", fg="blue", justify="left", wraplength=500)
        self.status_label.grid(row=8, column=0, columnspan=3, padx=8, pady=4)

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
        teams_chat_id = self.teams_chat_id_entry.get().strip()
        output_sqlite = self.output_var.get().strip()

        selection = self.file_listbox.curselection()
        workbook_id = self._files[selection[0]]["id"] if selection else ""

        error = validate_inputs(webhook_url, teams_notify_webhook_url, teams_chat_id, workbook_id, output_sqlite)
        if error:
            messagebox.showerror("입력 필요", error)
            return

        try:
            max_concurrency = parse_max_concurrency(self.concurrency_entry.get())
        except ValueError:
            messagebox.showerror("입력 오류", "동시 요청 수는 1 이상의 정수로 입력해주세요.")
            return

        self.config["webhook_url"] = webhook_url
        self.config["teams_notify_webhook_url"] = teams_notify_webhook_url
        self.config["teams_chat_id"] = teams_chat_id
        self.config["max_concurrency"] = max_concurrency
        save_config(self.config_path, self.config)

        self.run_button.config(state="disabled")
        self.status_label.config(text="처리 중입니다...")

        threading.Thread(
            target=self._run_pipeline,
            args=(webhook_url, teams_notify_webhook_url, teams_chat_id, workbook_id, output_sqlite, max_concurrency),
            daemon=True,
        ).start()

    def _notify(self, teams_notify_webhook_url: str, teams_chat_id: str, title: str, text: str) -> None:
        send_teams_chat_message(teams_notify_webhook_url, teams_chat_id, title, text)

    def _run_pipeline(
        self,
        webhook_url: str,
        teams_notify_webhook_url: str,
        teams_chat_id: str,
        workbook_id: str,
        output_sqlite: str,
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
                max_concurrency=max_concurrency,
            )
        except Exception as exc:
            self._notify(teams_notify_webhook_url, teams_chat_id, "DTC 등급 파이프라인 실패", f"오류: {exc}")
            self.root.after(0, self._on_done, f"실패: {exc}")
            return

        if stats["unmapped_sheets"]:
            self._notify(
                teams_notify_webhook_url,
                teams_chat_id,
                "DTC 등급 파이프라인 - 매핑 필요",
                build_unmapped_alert_message(stats, result),
            )
            self.root.after(0, self._on_done, f"매핑이 필요한 시트가 있습니다: {stats['unmapped_sheets']}")
        else:
            self._notify(
                teams_notify_webhook_url,
                teams_chat_id,
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
