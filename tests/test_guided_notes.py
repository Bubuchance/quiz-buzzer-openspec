from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.guided_notes import GuidedNotesError, fill_answers, parse_guided_notes
from app.sheets_url import SheetsUrlError, download_xlsx, spreadsheet_id
from samples.make_samples import SAMPLES


def make_xlsx(cells: dict[str, str], sheets: dict[str, dict[str, str]] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "S1"
    for ref, value in cells.items():
        ws[ref] = value
    for name, extra in (sheets or {}).items():
        other = wb.create_sheet(name)
        for ref, value in extra.items():
            other[ref] = value
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


# --- 2.1 佔位符掃描 ---

def test_placeholder_with_text_in_same_cell():
    qs = parse_guided_notes(make_xlsx({"B3": "牛頓第一定律又稱為 {{1}} 定律"}))
    assert [(q.number, q.sub_count) for q in qs] == [(1, 0)]
    assert qs[0].locations == ["S1!B3"]


def test_group_and_spaces_inside_braces():
    qs = parse_guided_notes(make_xlsx({"A1": "{{1}}", "A2": "{{ 2 - 1 }} 與 {{2-2}}"}))
    assert [(q.number, q.sub_count) for q in qs] == [(1, 0), (2, 2)]
    assert qs[1].is_group


def test_scans_all_sheets_any_position():
    data = make_xlsx({"Z99": "{{2}}"}, sheets={"另一頁": {"C7": "答：{{1}}", "K2": "{{3}}"}})
    qs = parse_guided_notes(data)
    assert [q.number for q in qs] == [1, 2, 3]
    assert qs[0].locations == ["另一頁!C7"]


def test_ignores_non_placeholder_braces_and_numbers():
    qs = parse_guided_notes(make_xlsx({"A1": "{1} {{a}} 123", "A2": "{{1}}"}))
    assert len(qs) == 1


# --- 2.2 匯入驗證 ---

@pytest.mark.parametrize(
    "cells, message",
    [
        ({"A1": "沒有佔位符"}, "找不到填空佔位符"),
        ({"A1": "{{1}}", "A2": "{{1}}"}, "重複"),
        ({"A1": "{{1}}", "A2": "{{1-1}}"}, "同時被標成單題和題組"),
        ({"A1": "{{1}}", "A2": "{{2}}", "A3": "{{4}}"}, "缺少第 3 題"),
        ({"A1": "{{2}}"}, "缺少第 1 題"),
        ({"A1": "{{0}}", "A2": "{{1}}"}, "從 1 開始"),
        ({"A1": "{{1-1}}", "A2": "{{1-3}}"}, "缺少第 1-2 小題"),
    ],
)
def test_invalid_guided_notes(cells, message):
    with pytest.raises(GuidedNotesError, match=message):
        parse_guided_notes(make_xlsx(cells))


def test_not_an_xlsx():
    with pytest.raises(GuidedNotesError, match="不是有效的 .xlsx"):
        parse_guided_notes(b"hello world")


# --- 2.3 答案寫回 ---

def test_fill_answers_keeps_text_format_and_unanswered():
    wb = Workbook()
    ws = wb.active
    ws["B3"] = "牛頓第一定律又稱為 {{1}} 定律"
    ws["B3"].font = Font(bold=True, color="FF0000")
    ws["B4"] = "題組：{{2-1}} / {{2-2}}"
    ws["B5"] = "未作答 {{3}}"
    ws["C1"] = "其他內容"
    out = BytesIO()
    wb.save(out)

    result = fill_answers(out.getvalue(), {(1, None): "慣性", (2, 1): "A", (2, 2): "=B"})
    filled = load_workbook(BytesIO(result)).active
    assert filled["B3"].value == "牛頓第一定律又稱為 慣性 定律"
    assert filled["B3"].font.bold and filled["B3"].font.color.rgb.endswith("FF0000")
    assert filled["B4"].value == "題組：A / =B"
    assert filled["B5"].value == "未作答 {{3}}"
    assert filled["C1"].value == "其他內容"


def test_answer_starting_with_equals_is_not_a_formula():
    result = fill_answers(make_xlsx({"A1": "{{1}}"}), {(1, None): "=1+1"})
    cell = load_workbook(BytesIO(result)).active["A1"]
    assert cell.value == "=1+1" and cell.data_type == "s"


# --- 2.4 Google Sheets 網址 ---

def test_spreadsheet_id_parsing():
    url = "https://docs.google.com/spreadsheets/d/abc_DEF-123/edit#gid=0"
    assert spreadsheet_id(url) == "abc_DEF-123"


@pytest.mark.parametrize("url", ["https://evil.com/spreadsheets/d/abc", "https://docs.google.com/document/d/x", "ftp://docs.google.com/spreadsheets/d/a"])
def test_bad_urls(url):
    with pytest.raises(SheetsUrlError):
        spreadsheet_id(url)


def test_download_success_uses_export_url():
    seen = []
    xlsx = make_xlsx({"A1": "{{1}}"})

    def fake_fetch(url):
        seen.append(url)
        return xlsx

    data = download_xlsx("https://docs.google.com/spreadsheets/d/XYZ/edit", fetch=fake_fetch)
    assert data == xlsx
    assert seen == ["https://docs.google.com/spreadsheets/d/XYZ/export?format=xlsx"]


def test_download_private_sheet_returns_html():
    with pytest.raises(SheetsUrlError, match="知道連結的人皆可檢視"):
        download_xlsx("https://docs.google.com/spreadsheets/d/XYZ", fetch=lambda u: b"<html>login</html>")


def test_download_network_error():
    def boom(url):
        raise OSError("network down")

    with pytest.raises(SheetsUrlError, match="無法下載"):
        download_xlsx("https://docs.google.com/spreadsheets/d/XYZ", fetch=boom)


# --- 2.5 範例檔 ---

def test_samples_import_with_expected_counts():
    expected = {"sample-single.xlsx": (5, []), "sample-group.xlsx": (5, [3, 5]), "sample-moved.xlsx": (3, [2])}
    for name, build in SAMPLES.items():
        qs = parse_guided_notes(build())
        count, groups = expected[name]
        assert len(qs) == count, name
        assert [q.number for q in qs if q.is_group] == groups, name
