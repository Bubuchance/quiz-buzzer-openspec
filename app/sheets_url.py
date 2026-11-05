"""從「知道連結的人皆可檢視」的 Google Sheets 網址下載 xlsx，不需要任何 API 金鑰。"""
from __future__ import annotations

import re
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlparse

MAX_BYTES = 20 * 1024 * 1024
TIMEOUT_SECONDS = 15
_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")


class SheetsUrlError(ValueError):
    """網址錯誤或下載失敗，訊息可直接顯示給老師。"""


def spreadsheet_id(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or parsed.hostname != "docs.google.com":
        raise SheetsUrlError("請貼上 docs.google.com 的 Google Sheets 網址")
    match = _ID_RE.search(parsed.path)
    if not match:
        raise SheetsUrlError("網址中找不到試算表 ID（應包含 /spreadsheets/d/...）")
    return match.group(1)


def export_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"


def _default_fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "classroom-buzzer"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SheetsUrlError("試算表檔案太大（超過 20 MB）")
    return data


def download_xlsx(url: str, fetch: Callable[[str], bytes] = _default_fetch) -> bytes:
    sheet_id = spreadsheet_id(url)
    try:
        data = fetch(export_url(sheet_id))
    except SheetsUrlError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SheetsUrlError("無法下載試算表，請確認網址正確且已設為「知道連結的人皆可檢視」") from exc
    # xlsx 是 zip 檔，開頭為 PK；未公開時 Google 會回傳登入頁 HTML
    if not data.startswith(b"PK"):
        raise SheetsUrlError("下載到的不是試算表，請確認已設為「知道連結的人皆可檢視」")
    return data
