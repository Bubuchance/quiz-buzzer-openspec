"""Guided Notes 匯入與匯出（與 SpecKit 組一致的格式）。

規範：
- 學習單中有一列「標題列」，同時含有「題號」與「作答」兩個儲存格（任一列、欄位順序不限）。
- 標題列以下，題號欄是數字的列就是一題，該列的作答格是填空格。
- 題組：作答欄以（1）（2）…開頭，後續小題在相連的下方列，且題號欄為空。
系統依標題文字動態找位置，所以不依賴固定的儲存格。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO

from openpyxl import load_workbook

NUMBER_HEADER = "題號"
ANSWER_HEADER = "作答"
SUB_RE = re.compile(r"^\s*[（(]\s*(\d+)\s*[）)]")
SUB_WITH_FILL_RE = re.compile(r"^\s*[（(]\s*\d+\s*[）)][\s_＿]*")
NUMBER_RE = re.compile(r"^\s*(?:第\s*)?(\d+)\s*(?:題)?\s*[.．、]?\s*$")

# 答案的索引鍵：(題號, 小題號)；單題的小題號為 None
BlankKey = tuple[int, "int | None"]


class GuidedNotesError(ValueError):
    """學習單格式不符時拋出，訊息可直接顯示給老師。"""


@dataclass
class Question:
    number: int
    sub_count: int = 0  # 0 = 單題；>=1 = 題組小題數
    locations: list[str] = field(default_factory=list)  # 每個填空格，例：["學習單!C5"]

    @property
    def is_group(self) -> bool:
        return self.sub_count > 0

    def blank_keys(self) -> list[BlankKey]:
        if self.is_group:
            return [(self.number, k) for k in range(1, self.sub_count + 1)]
        return [(self.number, None)]


@dataclass
class _Parsed:
    sheet_title: str
    questions: list[Question]
    cells: dict[BlankKey, str]  # 填空格座標，例：{(3, 1): "C7"}


def _open_workbook(data: bytes):
    try:
        return load_workbook(BytesIO(data))
    except Exception as exc:  # openpyxl 對壞檔會拋出各種例外
        raise GuidedNotesError("不是有效的 .xlsx 檔案") from exc


def _text(value) -> str:
    return "" if value is None else str(value)


def _compact(value) -> str:
    return re.sub(r"\s+", "", _text(value))


def _parse_number(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    match = NUMBER_RE.match(str(value))
    return int(match.group(1)) if match else None


def _find_header(workbook):
    """回傳 (工作表, 標題列號, 題號欄號, 作答欄號)；找不到回傳 None。"""
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            number_col = answer_col = None
            for cell in row:
                text = _compact(cell.value)
                if text == NUMBER_HEADER and number_col is None:
                    number_col = cell.column
                elif text == ANSWER_HEADER and answer_col is None:
                    answer_col = cell.column
            if number_col and answer_col:
                return sheet, row[0].row, number_col, answer_col
    return None


def _parse(workbook) -> _Parsed:
    header = _find_header(workbook)
    if header is None:
        raise GuidedNotesError(f"找不到同時含「{NUMBER_HEADER}」與「{ANSWER_HEADER}」的欄位標題列")
    sheet, header_row, number_col, answer_col = header

    cells: dict[BlankKey, str] = {}
    order: list[int] = []
    subs: dict[int, list[int]] = {}
    current: int | None = None  # 目前可以接續小題的題組題號

    for r in range(header_row + 1, sheet.max_row + 1):
        number_cell = sheet.cell(row=r, column=number_col)
        answer_cell = sheet.cell(row=r, column=answer_col)
        number = _parse_number(number_cell.value)
        sub_match = SUB_RE.match(_text(answer_cell.value))

        if number is not None:
            if number in subs or (number, None) in cells:
                raise GuidedNotesError(f"第 {number} 題重複（{sheet.title}!{number_cell.coordinate}）")
            order.append(number)
            if sub_match:
                k = int(sub_match.group(1))
                subs[number] = [k]
                cells[(number, k)] = answer_cell.coordinate
                current = number
            else:
                cells[(number, None)] = answer_cell.coordinate
                current = None
        elif _compact(number_cell.value) == "" and sub_match:
            k = int(sub_match.group(1))
            if current is None:
                raise GuidedNotesError(
                    f"{sheet.title}!{answer_cell.coordinate} 的（{k}）上方沒有所屬的題組題號"
                )
            if k in subs[current]:
                raise GuidedNotesError(f"第 {current} 題的第（{k}）小題重複")
            subs[current].append(k)
            cells[(current, k)] = answer_cell.coordinate
        else:
            current = None  # 空白列或段落標題：略過，題組不再接續

    if not order:
        raise GuidedNotesError("標題列下方沒有任何題目（題號欄需為數字）")

    numbers = sorted(order)
    if numbers[0] != 1:
        raise GuidedNotesError("題號必須從 1 開始" if numbers[0] == 0 else "題號不連續，缺少第 1 題")
    for expected, actual in enumerate(numbers, start=1):
        if actual != expected:
            raise GuidedNotesError(f"題號不連續，缺少第 {expected} 題")

    questions: list[Question] = []
    for n in numbers:
        if n in subs:
            ks = sorted(subs[n])
            for expected, actual in enumerate(ks, start=1):
                if actual != expected:
                    raise GuidedNotesError(f"第 {n} 題的小題號不連續，缺少第（{expected}）小題")
            locs = [f"{sheet.title}!{cells[(n, k)]}" for k in ks]
            questions.append(Question(n, len(ks), locs))
        else:
            questions.append(Question(n, 0, [f"{sheet.title}!{cells[(n, None)]}"]))
    return _Parsed(sheet.title, questions, cells)


def parse_guided_notes(data: bytes) -> list[Question]:
    """依欄位標題解析並驗證，回傳依題號排序的題目清單。"""
    return _parse(_open_workbook(data)).questions


def fill_answers(data: bytes, answers: dict[BlankKey, str]) -> bytes:
    """把答案寫回原檔：單題寫入作答格；題組取代（k）標示；沒有答案的格子不動。"""
    workbook = _open_workbook(data)
    parsed = _parse(workbook)
    sheet = workbook[parsed.sheet_title]
    for key, coordinate in parsed.cells.items():
        answer = answers.get(key)
        if answer is None:
            continue
        cell = sheet[coordinate]
        if key[1] is None:
            cell.value = answer
        else:
            cell.value = SUB_WITH_FILL_RE.sub(lambda _m: answer, _text(cell.value), count=1)
        cell.data_type = "s"  # 答案若以 "=" 開頭，避免被當成公式
    out = BytesIO()
    workbook.save(out)
    return out.getvalue()
