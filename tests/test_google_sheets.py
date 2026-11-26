import json

import gspread
import pytest

from app.google_sheets import GoogleSheetsGateway, SheetsError, error_for_status, spreadsheet_id, spreadsheet_url

EMAIL = "buzzer@demo-project.iam.gserviceaccount.com"


# --- 試算表 ID ---

def test_spreadsheet_id_from_url_and_bare_id():
    url = "https://docs.google.com/spreadsheets/d/12uh5xhIx2wXFMy42KU8lN7rLFQ8GDugt9zfAFEvu-1E/edit?gid=1167716485#gid=1167716485"
    assert spreadsheet_id(url) == "12uh5xhIx2wXFMy42KU8lN7rLFQ8GDugt9zfAFEvu-1E"
    assert spreadsheet_id("  12uh5xhIx2wXFMy42KU8lN7rLFQ8GDugt9zfAFEvu-1E ") == "12uh5xhIx2wXFMy42KU8lN7rLFQ8GDugt9zfAFEvu-1E"
    assert spreadsheet_url("abc") == "https://docs.google.com/spreadsheets/d/abc/edit"


@pytest.mark.parametrize("text", ["", "hello", "https://evil.com/spreadsheets/d/abcdefghijklmnopqrstuvwxyz",
                                  "https://docs.google.com/document/d/abc", "ftp://docs.google.com/spreadsheets/d/a"])
def test_bad_spreadsheet_ids(text):
    with pytest.raises(SheetsError, match="請貼上 Google Sheets 網址"):
        spreadsheet_id(text)


# --- 錯誤翻譯 ---

def test_error_messages():
    assert EMAIL in error_for_status(403, EMAIL).message and "編輯者" in error_for_status(403, EMAIL).message
    assert error_for_status(404, EMAIL).message.startswith("找不到試算表")
    assert error_for_status(429, None).status == 429
    assert "500" in error_for_status(500, None).message


# --- 金鑰設定 ---

def test_missing_credentials(tmp_path):
    gw = GoogleSheetsGateway(str(tmp_path / "nope.json"))
    status = gw.status()
    assert status["configured"] is False and status["service_account_email"] is None and "README" in status["hint"]
    with pytest.raises(SheetsError, match="尚未設定 Google 服務帳號") as exc:
        gw.read("abc")
    assert exc.value.status == 503


def test_credentials_from_environment(tmp_path, monkeypatch):
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"client_email": EMAIL}), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(key))
    status = GoogleSheetsGateway().status()
    assert status == {"configured": True, "service_account_email": EMAIL, "credentials_file": str(key), "hint": None}


# --- 以假的 gspread 用戶端測試讀寫呼叫 ---

class FakeWorksheet:
    def __init__(self, title, rows):
        self.title, self.rows, self.updates = title, rows, []

    def get_all_values(self):
        return self.rows

    def batch_update(self, data, value_input_option=None):
        self.updates.append((data, value_input_option))


class FakeBook:
    title = "軟工期末專案_題組_範例"

    def __init__(self):
        self.sheets = [FakeWorksheet("學習單", [["題號", "作答"], ["1", ""]])]

    def worksheets(self):
        return self.sheets

    def worksheet(self, title):
        for ws in self.sheets:
            if ws.title == title:
                return ws
        raise gspread.exceptions.WorksheetNotFound(title)


class FakeClient:
    def __init__(self, error=None):
        self.book, self.error = FakeBook(), error

    def open_by_key(self, key):
        if self.error:
            raise self.error
        return self.book


def gateway_with(client, tmp_path):
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"client_email": EMAIL}), encoding="utf-8")
    gw = GoogleSheetsGateway(str(key))
    gw._client = client
    return gw


def test_read_returns_all_sheets(tmp_path):
    book = gateway_with(FakeClient(), tmp_path).read("abc")
    assert book.title == "軟工期末專案_題組_範例"
    assert [(s.title, s.rows) for s in book.sheets] == [("學習單", [["題號", "作答"], ["1", ""]])]


def test_write_uses_raw_batch_update(tmp_path):
    client = FakeClient()
    gateway_with(client, tmp_path).write("abc", "學習單", {"B2": "=1+1", "B3": ""})
    assert client.book.sheets[0].updates == [
        ([{"range": "B2", "values": [["=1+1"]]}, {"range": "B3", "values": [[""]]}], "RAW")]


def test_write_missing_worksheet(tmp_path):
    with pytest.raises(SheetsError, match="找不到匯入時的工作表"):
        gateway_with(FakeClient(), tmp_path).write("abc", "別的工作表", {"A1": "x"})


def _api_error(code):
    err = gspread.exceptions.APIError.__new__(gspread.exceptions.APIError)
    err.code = code
    return err


@pytest.mark.parametrize("error, status, text", [
    (gspread.exceptions.SpreadsheetNotFound(), 404, "找不到試算表"),
    (_api_error(403), 403, EMAIL),
    (_api_error(404), 404, "找不到試算表"),
    (ConnectionError("down"), 502, "無法連線"),
])
def test_read_error_translation(tmp_path, error, status, text):
    with pytest.raises(SheetsError) as exc:
        gateway_with(FakeClient(error), tmp_path).read("abc")
    assert exc.value.status == status and text in exc.value.message
