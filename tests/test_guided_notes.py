from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.guided_notes import GuidedNotesError, fill_answers, parse_guided_notes
from app.sheets_url import SheetsUrlError, download_xlsx, spreadsheet_id
from samples.make_samples import SAMPLES, group_workbook


def make_xlsx(rows, start_row=1, cols=("題號", "題目", "作答"), extra_first_sheet=False) -> bytes:
    """rows：每列對應 cols 的值；start_row 為標題列的列號。"""
    wb = Workbook()
    ws = wb.active
    if extra_first_sheet:
        ws.title = "封面"
        ws["A1"] = "沒有標題列的封面"
        ws = wb.create_sheet("S")
    else:
        ws.title = "S"
    for c, name in enumerate(cols, start=1):
        ws.cell(row=start_row, column=c, value=name)
    for r, row in enumerate(rows, start=start_row + 1):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def summary(qs):
    return [(q.number, q.sub_count) for q in qs]


# --- 1.1 解析 ---

def test_basic_singles_and_locations():
    qs = parse_guided_notes(make_xlsx([(1, "a", None), (2, "b", None)]))
    assert summary(qs) == [(1, 0), (2, 0)]
    assert qs[0].locations == ["S!C2"]


def test_header_moved_and_column_order_changed():
    data = make_xlsx([(None, "q1", 1), (None, "q2", 2)], start_row=4, cols=("作答", "題目", "題號"))
    qs = parse_guided_notes(data)
    assert summary(qs) == [(1, 0), (2, 0)]
    assert qs[0].locations == ["S!A5"]


def test_first_sheet_with_header_is_used():
    qs = parse_guided_notes(make_xlsx([(1, "a", None)], extra_first_sheet=True))
    assert qs[0].locations == ["S!C2"]


def test_group_across_rows_full_and_half_width():
    data = make_xlsx([(1, "a", None), (2, "b", "（1）"), (None, "", "(2)"), (None, "", "（ 3 ）___"), (3, "c", None)])
    assert summary(parse_guided_notes(data)) == [(1, 0), (2, 3), (3, 0)]


def test_non_question_rows_skipped():
    data = make_xlsx([("【第一部分】", "", None), (1, "a", None), (None, "", None), (None, "段落說明", ""), (2, "b", None)])
    assert summary(parse_guided_notes(data)) == [(1, 0), (2, 0)]


@pytest.mark.parametrize("value", [3, 3.0, "3", "3.", "第3題", " 3 "])
def test_number_formats(value):
    data = make_xlsx([(1, "", None), (2, "", None), (value, "", None)])
    assert len(parse_guided_notes(data)) == 3


def test_header_with_spaces():
    assert len(parse_guided_notes(make_xlsx([(1, "", None)], cols=("題 號", "題目", " 作答 ")))) == 1


# --- 1.2 驗證 ---

@pytest.mark.parametrize(
    "rows, message",
    [
        ([(2, "", None)], "缺少第 1 題"),
        ([(1, "", None), (2, "", None), (4, "", None)], "缺少第 3 題"),
        ([(1, "", None), (1, "", None)], "第 1 題重複"),
        ([(0, "", None), (1, "", None)], "從 1 開始"),
        ([(1, "", "（1）"), (None, "", "（3）")], "缺少第（2）小題"),
        ([(1, "", "（1）"), (None, "", "（1）")], "小題重複"),
        ([(None, "", "（1）"), (1, "", None)], "沒有所屬的題組"),
        ([(1, "", None), (None, "", "（2）")], "沒有所屬的題組"),
        ([("說明", "", None)], "沒有任何題目"),
    ],
)
def test_invalid_sheets(rows, message):
    with pytest.raises(GuidedNotesError, match=message):
        parse_guided_notes(make_xlsx(rows))


def test_no_header():
    wb = Workbook()
    wb.active["A1"] = "題目"
    out = BytesIO()
    wb.save(out)
    with pytest.raises(GuidedNotesError, match="找不到同時含「題號」與「作答」"):
        parse_guided_notes(out.getvalue())


def test_not_an_xlsx():
    with pytest.raises(GuidedNotesError, match="不是有效的 .xlsx"):
        parse_guided_notes(b"hello world")


# --- 1.3 寫回 ---

def test_fill_answers_singles_groups_and_blanks():
    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    ws.append(["標題"])
    ws.append(["題號", "題目", "作答"])
    ws.append([1, "牛頓第一定律又稱為 ____ 定律", None])
    ws.append([2, "題組", "（1）____"])
    ws.append([None, "", "（2）"])
    ws.append([3, "沒人答", None])
    ws.append([4, "沒人答的題組", "（1）"])
    ws["B3"].font = Font(bold=True, color="FF0000")
    out = BytesIO()
    wb.save(out)

    result = fill_answers(out.getvalue(), {(1, None): "慣性", (2, 1): "A", (2, 2): "=B"})
    filled = load_workbook(BytesIO(result))["S"]
    assert filled["C3"].value == "慣性"
    assert filled["C4"].value == "A"
    assert filled["C5"].value == "=B" and filled["C5"].data_type == "s"
    assert filled["C6"].value is None
    assert filled["C7"].value == "（1）"
    assert filled["B3"].value == "牛頓第一定律又稱為 ____ 定律" and filled["B3"].font.bold
    assert filled["A1"].value == "標題"


def test_fill_answers_on_moved_sample():
    data = SAMPLES["sample-moved.xlsx"]()
    result = fill_answers(data, {(1, None): "80", (2, 1): "SYN", (2, 2): "SYN-ACK", (3, None): "IP 位址"})
    ws = load_workbook(BytesIO(result))["內容"]
    assert (ws["B6"].value, ws["B7"].value, ws["B8"].value, ws["B11"].value) == ("80", "SYN", "SYN-ACK", "IP 位址")
    assert ws["C5"].value == "【第一部分】"


# --- Google Sheets 網址（不變） ---

def test_spreadsheet_id_parsing():
    assert spreadsheet_id("https://docs.google.com/spreadsheets/d/abc_DEF-123/edit#gid=0") == "abc_DEF-123"


@pytest.mark.parametrize("url", ["https://evil.com/spreadsheets/d/abc", "https://docs.google.com/document/d/x", "ftp://docs.google.com/spreadsheets/d/a"])
def test_bad_urls(url):
    with pytest.raises(SheetsUrlError):
        spreadsheet_id(url)


def test_download_success_uses_export_url():
    seen = []
    xlsx = group_workbook()

    def fake_fetch(url):
        seen.append(url)
        return xlsx

    assert download_xlsx("https://docs.google.com/spreadsheets/d/XYZ/edit", fetch=fake_fetch) == xlsx
    assert seen == ["https://docs.google.com/spreadsheets/d/XYZ/export?format=xlsx"]


def test_download_private_sheet_returns_html():
    with pytest.raises(SheetsUrlError, match="知道連結的人皆可檢視"):
        download_xlsx("https://docs.google.com/spreadsheets/d/XYZ", fetch=lambda u: b"<html>login</html>")


def test_download_network_error():
    def boom(url):
        raise OSError("network down")

    with pytest.raises(SheetsUrlError, match="無法下載"):
        download_xlsx("https://docs.google.com/spreadsheets/d/XYZ", fetch=boom)


# --- 1.4 範例檔 ---

def test_samples_import_with_expected_counts():
    expected = {"sample-single.xlsx": (5, []), "sample-group.xlsx": (5, [3, 5]), "sample-moved.xlsx": (3, [2])}
    for name, build in SAMPLES.items():
        qs = parse_guided_notes(build())
        count, groups = expected[name]
        assert len(qs) == count, name
        assert [q.number for q in qs if q.is_group] == groups, name
