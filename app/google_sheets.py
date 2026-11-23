"""直接讀寫雲端 Google Sheets（Google Sheets API，服務帳號授權）。

金鑰檔放在本機，路徑由環境變數 GOOGLE_SERVICE_ACCOUNT_FILE 指定，
預設 credentials/service-account.json；credentials/ 不進 repo。
老師要把試算表「共用」給服務帳號的 email（編輯者）。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from app.guided_notes import SheetGrid, Spreadsheet

DEFAULT_CREDENTIALS = "credentials/service-account.json"
SETUP_HINT = "請依 README「設定 Google Sheets 串接」建立服務帳號，並把金鑰放在 credentials/service-account.json"
_ID_IN_PATH = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
_BARE_ID = re.compile(r"^[a-zA-Z0-9_-]{20,}$")


class SheetsError(Exception):
    """存取 Google Sheets 失敗；status 對應 HTTP 狀態碼，message 直接顯示給老師。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def spreadsheet_id(text: str) -> str:
    """從 Google Sheets 網址取出試算表 ID；也接受直接貼 ID。"""
    text = (text or "").strip()
    if _BARE_ID.match(text):
        return text
    parsed = urlparse(text)
    if parsed.scheme in ("http", "https") and parsed.hostname == "docs.google.com":
        match = _ID_IN_PATH.search(parsed.path)
        if match:
            return match.group(1)
    raise SheetsError("請貼上 Google Sheets 網址（https://docs.google.com/spreadsheets/d/...）")


def spreadsheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"


def error_for_status(status: int | None, email: str | None) -> SheetsError:
    """把 Google Sheets API 的錯誤翻成老師看得懂的訊息。"""
    if status == 403:
        who = email or "系統的服務帳號"
        return SheetsError(f"沒有權限：請在 Google Sheets 按「共用」，把 {who} 加為「編輯者」", 403)
    if status == 404:
        return SheetsError("找不到試算表，請確認網址是否正確", 404)
    if status == 429:
        return SheetsError("Google Sheets 請求太頻繁，請稍等一分鐘再試", 429)
    return SheetsError(f"Google Sheets 回應錯誤（{status}），請稍後再試", 502)


class SheetsGateway(Protocol):
    def status(self) -> dict: ...
    def read(self, sheet_id: str) -> Spreadsheet: ...
    def write(self, sheet_id: str, sheet_title: str, updates: dict[str, str]) -> None: ...


class GoogleSheetsGateway:
    """用 gspread 以服務帳號存取 Google Sheets。"""

    def __init__(self, credentials_file: str | None = None):
        self.credentials_file = Path(credentials_file or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE") or DEFAULT_CREDENTIALS)
        self._client = None

    @property
    def email(self) -> str | None:
        try:
            return json.loads(self.credentials_file.read_text(encoding="utf-8")).get("client_email")
        except (OSError, ValueError):
            return None

    def status(self) -> dict:
        email = self.email
        return {"configured": email is not None, "service_account_email": email,
                "credentials_file": str(self.credentials_file), "hint": None if email else SETUP_HINT}

    def _gspread(self):
        if self._client is None:
            if self.email is None:
                raise SheetsError("尚未設定 Google 服務帳號。" + SETUP_HINT, 503)
            import gspread

            try:
                self._client = gspread.service_account(filename=str(self.credentials_file))
            except Exception as exc:  # 金鑰內容錯誤
                raise SheetsError("Google 服務帳號金鑰無法使用。" + SETUP_HINT, 503) from exc
        return self._client

    def _call(self, func):
        import gspread

        try:
            return func()
        except SheetsError:
            raise
        except gspread.exceptions.SpreadsheetNotFound as exc:
            raise error_for_status(404, self.email) from exc
        except gspread.exceptions.APIError as exc:
            raise error_for_status(getattr(exc, "code", None), self.email) from exc
        except gspread.exceptions.WorksheetNotFound as exc:
            raise SheetsError("找不到匯入時的工作表，請重新匯入", 409) from exc
        except Exception as exc:  # 網路或授權連線問題
            raise SheetsError("無法連線到 Google Sheets，請確認網路連線", 502) from exc

    def read(self, sheet_id: str) -> Spreadsheet:
        client = self._gspread()

        def run():
            book = client.open_by_key(sheet_id)
            sheets = [SheetGrid(ws.title, ws.get_all_values()) for ws in book.worksheets()]
            return Spreadsheet(book.title, sheets)

        return self._call(run)

    def write(self, sheet_id: str, sheet_title: str, updates: dict[str, str]) -> None:
        client = self._gspread()

        def run():
            ws = client.open_by_key(sheet_id).worksheet(sheet_title)
            data = [{"range": a1, "values": [[value]]} for a1, value in updates.items()]
            ws.batch_update(data, value_input_option="RAW")  # RAW：純文字，不會變成公式

        self._call(run)
