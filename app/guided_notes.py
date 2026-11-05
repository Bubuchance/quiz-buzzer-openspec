"""Guided Notes 匯入與匯出。

規範：填空格用佔位符標記，單題 {{3}}，題組第 5 題的小題 {{5-1}}、{{5-2}}。
系統會掃描所有工作表、所有儲存格，所以不依賴固定的儲存格位置。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO

from openpyxl import load_workbook

PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)(?:\s*-\s*(\d+))?\s*\}\}")

# 答案的索引鍵：(題號, 小題號)；單題的小題號為 None
BlankKey = tuple[int, "int | None"]


class GuidedNotesError(ValueError):
    """Guided Notes 格式不符時拋出，訊息可直接顯示給老師。"""


@dataclass
class Question:
    number: int
    sub_count: int = 0  # 0 = 單題；>=1 = 題組小題數
    locations: list[str] = field(default_factory=list)  # 例：["工作表1!B3"]

    @property
    def is_group(self) -> bool:
        return self.sub_count > 0

    def blank_keys(self) -> list[BlankKey]:
        if self.is_group:
            return [(self.number, k) for k in range(1, self.sub_count + 1)]
        return [(self.number, None)]


def _open_workbook(data: bytes):
    try:
        return load_workbook(BytesIO(data))
    except Exception as exc:  # openpyxl 對壞檔會拋出各種例外
        raise GuidedNotesError("不是有效的 .xlsx 檔案") from exc


def _iter_string_cells(workbook):
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and "{{" in cell.value:
                    yield sheet, cell


def _label(key: BlankKey) -> str:
    number, sub = key
    return f"第 {number} 題" if sub is None else f"第 {number}-{sub} 小題"


def parse_guided_notes(data: bytes) -> list[Question]:
    """掃描佔位符並驗證，回傳依題號排序的題目清單。"""
    workbook = _open_workbook(data)
    found: dict[BlankKey, str] = {}
    for sheet, cell in _iter_string_cells(workbook):
        for match in PLACEHOLDER_RE.finditer(cell.value):
            number = int(match.group(1))
            sub = int(match.group(2)) if match.group(2) is not None else None
            key = (number, sub)
            where = f"{sheet.title}!{cell.coordinate}"
            if key in found:
                raise GuidedNotesError(
                    f"{_label(key)}的佔位符重複出現（{found[key]} 與 {where}）"
                )
            found[key] = where

    if not found:
        raise GuidedNotesError("找不到填空佔位符，請在填空格加上 {{題號}}，例如 {{1}}")

    singles = {n for n, s in found if s is None}
    groups: dict[int, list[int]] = {}
    for n, s in found:
        if s is not None:
            groups.setdefault(n, []).append(s)

    mixed = sorted(singles & groups.keys())
    if mixed:
        raise GuidedNotesError(f"第 {mixed[0]} 題同時被標成單題和題組，請擇一")

    numbers = sorted(singles | groups.keys())
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
        if 0 in numbers:
            raise GuidedNotesError("題號必須從 1 開始")
        raise GuidedNotesError(f"題號不連續，缺少第 {missing[0]} 題")

    questions: list[Question] = []
    for n in numbers:
        if n in groups:
            subs = sorted(groups[n])
            if subs != list(range(1, len(subs) + 1)):
                missing = sorted(set(range(1, max(subs) + 1)) - set(subs))
                if 0 in subs:
                    raise GuidedNotesError(f"第 {n} 題的小題號必須從 1 開始")
                raise GuidedNotesError(f"第 {n} 題的小題號不連續，缺少第 {n}-{missing[0]} 小題")
            locations = [found[(n, s)] for s in subs]
            questions.append(Question(n, len(subs), locations))
        else:
            questions.append(Question(n, 0, [found[(n, None)]]))
    return questions


def fill_answers(data: bytes, answers: dict[BlankKey, str]) -> bytes:
    """把答案寫回原檔的佔位符位置；沒有答案的佔位符保留原樣。"""
    workbook = _open_workbook(data)

    def replace(match: re.Match) -> str:
        number = int(match.group(1))
        sub = int(match.group(2)) if match.group(2) is not None else None
        answer = answers.get((number, sub))
        return match.group(0) if answer is None else answer

    for _sheet, cell in list(_iter_string_cells(workbook)):
        new_value = PLACEHOLDER_RE.sub(replace, cell.value)
        if new_value != cell.value:
            cell.value = new_value
            # 答案若以 "=" 開頭，避免被當成公式執行
            cell.data_type = "s"

    out = BytesIO()
    workbook.save(out)
    return out.getvalue()
