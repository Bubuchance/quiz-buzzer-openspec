# Design

## Context

學習單解析規則（欄位標題、題組（k））與活動規則不變（見 `openspec/specs/`）。本 change 只替換「資料從哪裡來、寫到哪裡去」：從 xlsx 檔改為 Google Sheets API（動機見 proposal.md）。

## Goals / Non-Goals

**Goals:**
- 匯入與寫回都直接對雲端試算表操作，沒有任何 xlsx 中間檔。
- 金鑰不進 repo；設定錯誤時老師看得懂該怎麼修。
- 解析與寫回規則不依賴網路，仍可完整單元測試。

**Non-Goals:**
- 不做 OAuth 使用者登入流程。
- 不監聽試算表變更（匯入是一次性讀取；寫回前再讀一次比對）。

## Decisions

### D1. 授權：Google 服務帳號
- 金鑰檔路徑讀環境變數 `GOOGLE_SERVICE_ACCOUNT_FILE`，預設 `credentials/service-account.json`；`.gitignore` 排除 `credentials/` 與 `*service-account*.json`。
- 服務帳號 email 從金鑰檔的 `client_email` 讀出，顯示在老師頁，老師把試算表共用給它（編輯者）。
- **替代方案**：OAuth 使用者登入（需同意畫面、測試使用者、token 檔，步驟多）；Apps Script（每份試算表都要部署腳本，換學習單就要重做）。

### D2. 套件：gspread
- `gspread` 是常用的 Google Sheets API 用戶端，內建服務帳號登入。讀取用 `worksheet.get_all_values()`（每格的顯示文字，合併儲存格只有左上角有值，與 xlsx 行為相同）；寫入用 `worksheet.batch_update(..., value_input_option="RAW")`，一次送出所有作答格，並以純文字寫入。
- **替代方案**：`google-api-python-client`（較底層、程式較長）。

### D3. 抽象層：值格線（grid）＋閘道（gateway）
- `guided_notes.py` 只處理純資料：`Spreadsheet(title, sheets=[SheetGrid(title, rows)])`，`rows` 是字串二維陣列。解析輸出題目清單、每個填空格的列欄位置與原始文字。
- `build_writes(parsed, answers)` 產生 `{"G5": "CPU", "G6": "（2）堆疊", ...}`，涵蓋所有填空格（無人成功的也寫入空白或（k））。
- `google_sheets.py` 的 `GoogleSheetsGateway` 負責 API 呼叫與錯誤翻譯；`create_app(gateway=...)` 可注入假閘道，測試與瀏覽器 E2E 都不需連網。
- 測試與範例檔用 `spreadsheet_from_xlsx()` 把 xlsx 轉成同樣的格線（只在測試／範例使用，系統執行時不處理 xlsx）。

### D4. 寫回流程
1. 活動必須「已結束」，且有匯入來源（試算表 ID）。
2. 重新讀取雲端試算表並解析；題號清單或任一題的小題數與匯入時不同 → 拒絕（409），提示重新匯入。
3. 依成功答案組出更新內容，對解析出的工作表做一次 `batch_update`。
4. 回傳寫入格數與試算表網址，老師頁顯示提示與連結。

### D5. 題組寫回格式「（k）答案」
- 保留原儲存格的（k）標示原文（全形或半形）再接答案。寫回後題組格仍以（k）開頭，所以可再次匯入、再次寫回（覆蓋舊答案）。
- 單題無人成功時寫入空白，避免「重設後再玩一輪」留下上一輪的答案。

### D6. 錯誤翻譯
| 狀況 | 訊息 |
|------|------|
| 金鑰檔不存在／格式錯誤 | 尚未設定 Google 服務帳號，請依 README 設定 `credentials/service-account.json` |
| API 403 | 沒有權限：請在 Google Sheets 按「共用」，把 `<email>` 加為「編輯者」 |
| API 404／找不到 | 找不到試算表，請確認網址 |
| 其他 API 錯誤 | Google Sheets 回應錯誤（狀態碼） |
| 網路錯誤 | 無法連線到 Google，請確認網路 |

### D7. API 變更
- 移除 `POST /api/teacher/import/file`、`GET /api/teacher/export/guided-notes`。
- `POST /api/teacher/import/url` 改用閘道讀取。
- 新增 `GET /api/teacher/sheets-status`（是否已設定、服務帳號 email）、`POST /api/teacher/export/google-sheets`（寫回）。
- 快照加入 `spreadsheet_url`。

## Risks / Trade-offs

- [學校 Google Workspace 帳號可能禁止建立服務帳號金鑰] → README 建議用個人 Gmail 建立 Google Cloud 專案；試算表本身可以在任何帳號，只要共用給服務帳號即可。
- [開發環境無法連到 Google API] → 讀寫邏輯以假閘道測試；真正連線需組員在自己電腦依人工驗證清單確認。
- [Sheets API 有每分鐘請求上限] → 匯入每個工作表一次請求、寫回一次批次請求，遠低於上限。

## Migration Plan

1. 依 README 建立服務帳號、下載金鑰到 `credentials/service-account.json`。
2. 把學習單共用給服務帳號 email（編輯者）。
3. 啟動系統，貼上試算表網址匯入。
