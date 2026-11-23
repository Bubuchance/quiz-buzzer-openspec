# Tasks

## 1. 解析改為值格線（guided-notes）

- [x] 1.1 `app/guided_notes.py` 改以 `Spreadsheet`／`SheetGrid` 字串格線解析（規則不變），並提供測試用的 `spreadsheet_from_xlsx()`；以既有解析與驗證測試全數通過確認
- [x] 1.2 實作 `build_writes()`：單題寫答案或空白、題組寫「（k）答案」或「（k）」，並以單元測試驗證；另測試寫回後的格線再次解析題目結構不變

## 2. Google Sheets 閘道與授權

- [x] 2.1 新增 `app/google_sheets.py`：試算表 ID 解析、`GoogleSheetsGateway`（gspread 讀取所有工作表、RAW 批次寫入）、金鑰檔路徑設定、服務帳號 email、錯誤翻譯，並以單元測試驗證 ID 解析、未設定金鑰與各錯誤訊息
- [x] 2.2 `requirements.txt` 加入 `gspread`、移除 `app/sheets_url.py`，`.gitignore` 排除 `credentials/` 與服務帳號金鑰檔，並確認 `git check-ignore` 生效

## 3. 活動與 API

- [x] 3.1 `app/activity.py`：匯入改收格線與試算表 ID；新增 `prepare_writeback()`（須已結束、結構比對、產生更新），並以單元測試驗證
- [x] 3.2 `app/main.py`：匯入改用閘道、新增 `sheets-status` 與 `export/google-sheets`、移除 xlsx 上傳與下載，並以注入假閘道的 TestClient 測試成功、權限錯誤、結構改變、未結束等情境

## 4. 前端與文件

- [x] 4.1 老師頁：移除上傳表單、顯示服務帳號狀態與共用提示、「寫回 Google Sheets」按鈕與結果提示，並以瀏覽器（假閘道）確認
- [x] 4.2 README 加入 Google Cloud 服務帳號設定步驟與共用說明、更新人工驗證清單與 SpecKit 對齊清單，並確認文件中不再出現下載 xlsx 的流程

## 5. 整合驗證

- [x] 5.1 `pytest` 全部通過、`openspec validate --all --strict` 通過，並以瀏覽器（假閘道）完成老師＋2 組流程到寫回

## Workflow follow-up

- `/opsx:verify connect-google-sheets` → `/opsx:sync connect-google-sheets` → `/opsx:archive connect-google-sheets`
- 組員在自己電腦設定服務帳號，用老師範本實際測試匯入與寫回。
