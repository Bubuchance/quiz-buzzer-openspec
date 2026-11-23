from io import BytesIO

import pytest
from openpyxl import Workbook

from app.guided_notes import (GuidedNotesError, SheetGrid, Spreadsheet, build_writes, column_letter,
                              parse_spreadsheet, spreadsheet_from_xlsx)
from samples.make_samples import SAMPLES


def parse_guided_notes(data: bytes):
    """測試輔助：xlsx → 與 Google Sheets API 相同的值格線 → 解析。"""
    return parse_spreadsheet(spreadsheet_from_xlsx(data)).questions


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


# --- 1.3 寫回內容（build_writes） ---

def grid(rows, title="S"):
    return Spreadsheet("t", [SheetGrid(title, rows)])


def test_column_letter():
    assert [column_letter(c) for c in (1, 7, 26, 27, 52)] == ["A", "G", "Z", "AA", "AZ"]


def test_build_writes_singles_groups_and_blanks():
    parsed = parse_spreadsheet(grid([
        ["標題"],
        ["題號", "題目", "作答"],
        ["1", "牛頓第一定律又稱為 ____ 定律", ""],
        ["2", "題組", "（1）"],
        ["", "", "(2)"],
        ["3", "沒人答", "舊答案"],
        ["4", "沒人答的題組", "（1）"],
    ]))
    writes = build_writes(parsed, {(1, None): "慣性", (2, 1): "A", (2, 2): "=B"})
    assert writes == {"C3": "慣性", "C4": "（1）A", "C5": "(2)=B", "C6": "", "C7": "（1）"}


def test_written_sheet_can_be_reimported_and_rewritten():
    rows = [["題號", "題目", "作答"], ["1", "", ""], ["2", "", "（1）"], ["", "", "（2）"]]
    parsed = parse_spreadsheet(grid(rows))
    writes = build_writes(parsed, {(1, None): "CPU", (2, 1): "演算法", (2, 2): "堆疊"})
    for a1, value in writes.items():  # 模擬寫回雲端後的試算表
        rows[int(a1[1:]) - 1][2] = value
    again = parse_spreadsheet(grid(rows))
    assert again.structure() == parsed.structure() == [(1, 0), (2, 2)]
    assert build_writes(again, {(2, 1): "新答案"}) == {"C2": "", "C3": "（1）新答案", "C4": "（2）"}


def test_build_writes_on_moved_sample():
    parsed = parse_spreadsheet(spreadsheet_from_xlsx(SAMPLES["sample-moved.xlsx"]()))
    assert parsed.sheet_title == "內容"
    writes = build_writes(parsed, {(1, None): "80", (2, 1): "SYN", (2, 2): "SYN-ACK", (3, None): "IP 位址"})
    assert writes == {"B6": "80", "B7": "(1)SYN", "B8": "(2)SYN-ACK", "B11": "IP 位址"}


def test_ragged_rows_and_none_values():
    parsed = parse_spreadsheet(grid([["題號", None, "作答"], ["1"], ["2", "x"]]))
    assert parsed.structure() == [(1, 0), (2, 0)] and parsed.cells[(1, None)] == "C2"


# --- 1.4 範例檔 ---

def test_samples_import_with_expected_counts():
    expected = {"sample-single.xlsx": (5, []), "sample-group.xlsx": (5, [3, 5]), "sample-moved.xlsx": (3, [2]),
                "teacher-layout-single.xlsx": (6, []), "teacher-layout-group.xlsx": (4, [1, 2])}
    for name, build in SAMPLES.items():
        qs = parse_guided_notes(build())
        count, groups = expected[name]
        assert len(qs) == count, name
        assert [q.number for q in qs if q.is_group] == groups, name


# --- 老師範本版面（合併儲存格、分隔列、題號上下合併） ---

def test_teacher_single_layout_locations():
    qs = parse_guided_notes(SAMPLES["teacher-layout-single.xlsx"]())
    assert [q.locations for q in qs[:3]] == [["學習單!G5"], ["學習單!G7"], ["學習單!G9"]]


def test_teacher_group_layout_and_writes():
    data = SAMPLES["teacher-layout-group.xlsx"]()
    parsed = parse_spreadsheet(spreadsheet_from_xlsx(data))
    assert [(q.number, q.sub_count, q.locations) for q in parsed.questions] == [
        (1, 2, ["學習單!G5", "學習單!G6"]), (2, 2, ["學習單!G8", "學習單!G9"]),
        (3, 0, ["學習單!G11"]), (4, 0, ["學習單!G13"]),
    ]
    writes = build_writes(parsed, {(1, 1): "CPU", (1, 2): "作業系統", (3, None): "0"})
    assert writes == {"G5": "（1）CPU", "G6": "（2）作業系統", "G8": "（1）", "G9": "（2）", "G11": "0", "G13": ""}
