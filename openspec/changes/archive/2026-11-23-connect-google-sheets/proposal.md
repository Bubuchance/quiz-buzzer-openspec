# Proposal

## Why

課程公告（11-17）補充說明：Guided Notes 必須由系統**直接串接雲端線上的 Google Sheets 進行讀寫**，而非下載成 .xlsx 在本地端離線處理。目前系統的匯入（上傳 xlsx、公開網址下載 xlsx）與匯出（下載 xlsx 再手動匯入）都屬於離線處理，必須改為以 Google Sheets API 即時讀寫（分析見 `docs/08-explore-串接GoogleSheets.md`）。

## What Changes

- **BREAKING** 移除 .xlsx 上傳匯入與公開網址下載 xlsx 匯入；改為老師貼上自己 Google Sheets 的網址，系統以 Google Sheets API 即時讀取。
- **BREAKING** 移除下載 xlsx 的匯出；改為搶答結束後由系統直接把答案寫回雲端試算表的作答格。
- 寫回前重新讀取雲端試算表並比對題目結構，不一致時拒絕寫回。
- 題組寫回格式改為「（k）答案」（保留標示，寫回後可再次匯入）；無人成功的單題寫入空白。
- 新增 Google 服務帳號授權：金鑰檔放本機、以環境變數指定、不進 repo；老師頁顯示服務帳號 email 與設定狀態，並提供中文錯誤訊息。
- 學習單格式驗證不再檢查 .xlsx 檔案格式。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `guided-notes`：匯入來源改為雲端 Google Sheets、寫回改為直接寫入雲端、新增授權設定需求、格式驗證移除 .xlsx 條件。

## Impact

- 新增相依套件 `gspread`（Google Sheets API 用戶端，內含 `google-auth`）。
- 程式：`app/guided_notes.py` 改為解析與 Sheets API 相同的「值格線」；新增 `app/google_sheets.py`（讀寫與錯誤翻譯）；移除 `app/sheets_url.py`；`app/activity.py`、`app/main.py`、老師頁前端調整。
- `openpyxl` 只保留給範例檔產生與測試轉換用，系統執行時不再處理 xlsx。
- 使用者需在 Google Cloud 建立服務帳號並下載金鑰（README 提供步驟），並把學習單共用給該服務帳號。
- 需通知 SpecKit 組：授權方式與題組寫回格式。
