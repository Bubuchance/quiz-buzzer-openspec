"""Guided Notes 解析與寫回內容計算（與 SpecKit 組一致的格式）。

規範：
- 學習單中有一列「標題列」，同時含有「題號」與「作答」兩個儲存格（任一列、欄位順序不限）。
- 標題列以下，題號欄是數字的列就是一題，該列的作答格是填空格。
- 題組：作答欄以（1）（2）…開頭，後續小題在相連的下方列，且題號欄為空。

這個模組只處理「值格線」（每個工作表是一個字串二維陣列），資料來源是 Google Sheets API，
不碰網路也不處理檔案，方便單元測試。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NUMBER_HEADER = "題號"
ANSWER_HEADER = "作答"
SUB_RE = re.compile(r"^\s*([（(]\s*(\d+)\s*[）)])")
NUMBER_RE = re.compile(r"^\s*(?:第\s*)?(\d+)(?:\.0+)?\s*(?:題)?\s*[.．、]?\s*$")

# 答案的索引鍵：(題號, 小題號)；單題的小題號為 None
BlankKey = tuple[int, "int | None"]


class GuidedNotesError(ValueError):
    """學習單格式不符時拋出，訊息可直接顯示給老師。"""


@dataclass
class SheetGrid:
    """一個工作表的儲存格顯示文字；rows[0][0] 是 A1。合併儲存格只有左上角有值。"""
    title: str
    rows: list[list[str]]

    def value(self, row: int, col: int) -> str:  # 1-based
        if 1 <= row <= len(self.rows):
            cells = self.rows[row - 1]
            if 1 <= col <= len(cells):
                return "" if cells[col - 1] is None else str(cells[col - 1])
        return ""


@dataclass
class Spreadsheet:
    title: str
    sheets: list[SheetGrid]


@dataclass
class Question:
    number: int
    sub_count: int = 0  # 0 = 單題；>=1 = 題組小題數
    locations: list[str] = field(default_factory=list)  # 每個填空格，例：["學習單!G5"]

    @property
    def is_group(self) -> bool:
        return self.sub_count > 0

    def blank_keys(self) -> list[BlankKey]:
        if self.is_group:
            return [(self.number, k) for k in range(1, self.sub_count + 1)]
        return [(self.number, None)]


@dataclass
class ParsedNotes:
    sheet_title: str
    questions: list[Question]
    cells: dict[BlankKey, str]  # 填空格 A1 座標，例：{(3, 1): "G7"}
    labels: dict[BlankKey, str]  # 題組小題的原始（k）標示，例：{(3, 1): "（1）"}

    def structure(self) -> list[tuple[int, int]]:
        return [(q.number, q.sub_count) for q in self.questions]


def column_letter(col: int) -> str:
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _parse_number(value: str) -> int | None:
    match = NUMBER_RE.match(value or "")
    return int(match.group(1)) if match else None


def _find_header(spreadsheet: Spreadsheet):
    """回傳 (工作表, 標題列號, 題號欄號, 作答欄號)；找不到回傳 None。"""
    for sheet in spreadsheet.sheets:
        for r, cells in enumerate(sheet.rows, start=1):
            number_col = answer_col = None
            for c, value in enumerate(cells, start=1):
                text = _compact("" if value is None else str(value))
                if text == NUMBER_HEADER and number_col is None:
                    number_col = c
                elif text == ANSWER_HEADER and answer_col is None:
                    answer_col = c
            if number_col and answer_col:
                return sheet, r, number_col, answer_col
    return None


def parse_spreadsheet(spreadsheet: Spreadsheet) -> ParsedNotes:
    """依欄位標題解析並驗證；格式不符時拋出 GuidedNotesError。"""
    header = _find_header(spreadsheet)
    if header is None:
        raise GuidedNotesError(f"找不到同時含「{NUMBER_HEADER}」與「{ANSWER_HEADER}」的欄位標題列")
    sheet, header_row, number_col, answer_col = header
    answer_letter = column_letter(answer_col)

    cells: dict[BlankKey, str] = {}
    labels: dict[BlankKey, str] = {}
    order: list[int] = []
    subs: dict[int, list[int]] = {}
    current: int | None = None  # 目前可以接續小題的題組題號

    for r in range(header_row + 1, len(sheet.rows) + 1):
        number_text = sheet.value(r, number_col)
        answer_text = sheet.value(r, answer_col)
        number = _parse_number(number_text)
        sub_match = SUB_RE.match(answer_text)
        where = f"{answer_letter}{r}"

        if number is not None:
            if number in subs or (number, None) in cells:
                raise GuidedNotesError(f"第 {number} 題重複（{sheet.title}!{column_letter(number_col)}{r}）")
            order.append(number)
            if sub_match:
                k = int(sub_match.group(2))
                subs[number] = [k]
                cells[(number, k)] = where
                labels[(number, k)] = sub_match.group(1)
                current = number
            else:
                cells[(number, None)] = where
                current = None
        elif _compact(number_text) == "" and sub_match:
            k = int(sub_match.group(2))
            if current is None:
                raise GuidedNotesError(f"{sheet.title}!{where} 的（{k}）上方沒有所屬的題組題號")
            if k in subs[current]:
                raise GuidedNotesError(f"第 {current} 題的第（{k}）小題重複")
            subs[current].append(k)
            cells[(current, k)] = where
            labels[(current, k)] = sub_match.group(1)
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
            questions.append(Question(n, len(ks), [f"{sheet.title}!{cells[(n, k)]}" for k in ks]))
        else:
            questions.append(Question(n, 0, [f"{sheet.title}!{cells[(n, None)]}"]))
    return ParsedNotes(sheet.title, questions, cells, labels)


def build_writes(parsed: ParsedNotes, answers: dict[BlankKey, str]) -> dict[str, str]:
    """計算要寫回試算表的內容（A1 → 文字），涵蓋所有填空格：

    - 單題：成功答案；無人成功寫入空白。
    - 題組：「（k）答案」保留原標示；無人成功只寫「（k）」。寫回後仍可再次匯入。
    """
    writes: dict[str, str] = {}
    for key, a1 in parsed.cells.items():
        answer = answers.get(key)
        if key[1] is None:
            writes[a1] = answer or ""
        else:
            writes[a1] = parsed.labels[key] + (answer or "")
    return writes


def spreadsheet_from_xlsx(data: bytes, title: str = "xlsx") -> Spreadsheet:
    """把 xlsx 轉成與 Google Sheets API 相同的值格線。只供測試與範例檔使用。"""
    from io import BytesIO

    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(data))
    sheets = []
    for ws in workbook.worksheets:
        rows = [["" if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
                 for v in row] for row in ws.iter_rows(values_only=True)]
        sheets.append(SheetGrid(ws.title, rows))
    return Spreadsheet(title, sheets)
