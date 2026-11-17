"""產生三份範例 Guided Notes（xlsx），格式與 SpecKit 組一致，用於測試與 Demo。

執行：python samples/make_samples.py
產生：
- samples/sample-single.xlsx：5 題單題
- samples/sample-group.xlsx：單題與題組混合
- samples/sample-moved.xlsx：前面多一張封面工作表、標題列在第 4 列、欄位順序不同（驗證沒有寫死位置）
這些檔案也可以上傳到 Google Sheets（檔案 → 匯入）後，用網址匯入測試。
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

HERE = Path(__file__).resolve().parent
BOLD = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="D9E2F3")
ANSWER_FILL = PatternFill("solid", fgColor="FFF2CC")


def _save(wb: Workbook) -> bytes:
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def _sheet(ws, title: str, rows: list[tuple]) -> None:
    """欄位：A 題號、B 題目、C 作答；第 1 列標題文字、第 2 列欄位標題。"""
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    for col, text in enumerate(["題號", "題目", "作答"], start=1):
        cell = ws.cell(row=2, column=col, value=text)
        cell.font, cell.fill = BOLD, HEADER_FILL
    for r, (number, question, answer) in enumerate(rows, start=3):
        ws.cell(row=r, column=1, value=number)
        ws.cell(row=r, column=2, value=question).alignment = Alignment(wrap_text=True)
        ws.cell(row=r, column=3, value=answer).fill = ANSWER_FILL
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 24


def single_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Guided Notes"
    _sheet(ws, "第三章 軟體開發流程 Guided Notes（單題）", [
        (1, "瀑布式模型的階段依序為需求、設計、____、測試、維護。", None),
        (2, "敏捷開發中，固定長度的開發週期稱為 ____。", None),
        (3, "Scrum 中負責排定產品待辦清單優先順序的角色是 ____。", None),
        (4, "以規格驅動 AI 產生程式碼的開發方式簡稱 ____。", None),
        (5, "OpenSpec 中把 change 的規格合併到主規格的步驟叫做 ____。", None),
    ])
    return _save(wb)


def group_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Guided Notes"
    _sheet(ws, "第五章 UML Guided Notes（題組＋單題）", [
        (1, "描述物件之間訊息傳遞先後順序的圖是 ____。", None),
        (2, "描述系統由哪些元件組成的圖是 ____。", None),
        (3, "類別圖中，空心菱形代表 (1)____，實心菱形代表 (2)____。", "（1）"),
        (None, "", "（2）"),
        (4, "使用者與系統互動的情境用 ____ 圖表示。", None),
        (5, "SOLID 中 S 代表 (1)____，O 代表 (2)____，L 代表 (3)____。", "（1）"),
        (None, "", "（2）"),
        (None, "", "（3）"),
    ])
    return _save(wb)


def moved_workbook() -> bytes:
    """封面工作表在前；內容工作表標題列在第 4 列，欄位順序為 作答｜題目｜題號，中間有段落列。"""
    wb = Workbook()
    cover = wb.active
    cover.title = "封面"
    cover["B2"] = "期中複習（換位置版本）"
    ws = wb.create_sheet("內容")
    ws["A1"] = "網路概論 Guided Notes"
    ws["A2"] = "說明：請在作答欄填寫答案"
    for col, text in zip("BCE", ["作答", "題目", "題號"]):
        ws[f"{col}4"] = text
    ws["C5"] = "【第一部分】"
    ws["E6"], ws["C6"] = 1, "HTTP 預設使用的連接埠是 ____"
    ws["E7"], ws["C7"], ws["B7"] = "2", "TCP 三向交握依序為 (1)____、(2)____、ACK", "(1)"
    ws["B8"] = "(2)"
    ws["C10"] = "【第二部分】"
    ws["E11"], ws["C11"] = "第3題", "DNS 的用途是把網域名稱轉成 ____"
    return _save(wb)


SAMPLES = {
    "sample-single.xlsx": single_workbook,
    "sample-group.xlsx": group_workbook,
    "sample-moved.xlsx": moved_workbook,
}


def main() -> None:
    for name, build in SAMPLES.items():
        path = HERE / name
        path.write_bytes(build())
        print(f"已產生 {path}")


if __name__ == "__main__":
    main()
