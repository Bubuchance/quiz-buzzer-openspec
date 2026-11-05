"""產生三份範例 Guided Notes（xlsx），用於測試與 Demo。

執行：python samples/make_samples.py
產生：samples/sample-single.xlsx（單題）、samples/sample-group.xlsx（題組＋單題）、samples/sample-moved.xlsx（換位置）
這些檔案也可以上傳到 Google Sheets（檔案 → 匯入）後，用網址匯入測試。
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

HERE = Path(__file__).resolve().parent
TITLE_FONT = Font(bold=True, size=14)
BLANK_FILL = PatternFill("solid", fgColor="FFF2CC")


def _setup(ws, title: str) -> None:
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 60


def _row(ws, row: int, label: str, text: str) -> None:
    ws.cell(row=row, column=1, value=label)
    cell = ws.cell(row=row, column=2, value=text)
    cell.fill = BLANK_FILL
    cell.alignment = Alignment(wrap_text=True)


def single_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Guided Notes"
    _setup(ws, "第三章 軟體開發流程 Guided Notes（單題）")
    items = [
        "瀑布式模型的階段依序為需求、設計、{{1}}、測試、維護。",
        "敏捷開發中，固定長度的開發週期稱為 {{2}}。",
        "Scrum 中負責排定產品待辦清單優先順序的角色是 {{3}}。",
        "以規格驅動 AI 產生程式碼的開發方式簡稱 {{4}}。",
        "OpenSpec 中把 change 的規格合併到主規格的步驟叫做 {{5}}。",
    ]
    for i, text in enumerate(items, start=1):
        _row(ws, i + 2, f"{i}.", text)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def group_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Guided Notes"
    _setup(ws, "第五章 UML Guided Notes（題組＋單題）")
    _row(ws, 3, "1.", "描述物件之間訊息傳遞先後順序的圖是 {{1}}。")
    _row(ws, 4, "2.", "描述系統由哪些元件組成的圖是 {{2}}。")
    _row(ws, 5, "3.", "題組：類別圖中，空心菱形代表 {{3-1}}，實心菱形代表 {{3-2}}。")
    _row(ws, 6, "4.", "使用者與系統互動的情境用 {{4}} 圖表示。")
    _row(ws, 7, "5.", "題組：SOLID 中 S 代表 {{5-1}}，O 代表 {{5-2}}，L 代表 {{5-3}}。")
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def moved_workbook() -> bytes:
    """佔位符分散在兩個工作表、不同欄位，證明不是固定位置。"""
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "封面"
    ws1["D2"] = "期中複習（換位置版本）"
    ws1["F9"] = "HTTP 預設使用的連接埠是 {{1}}"
    ws2 = wb.create_sheet("內容")
    ws2["C4"] = "題組：TCP 三向交握依序為 {{2-1}}、{{2-2}}、ACK"
    ws2["H15"] = "{{3}}"
    ws2["G15"] = "DNS 的用途是把網域名稱轉成："
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


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
