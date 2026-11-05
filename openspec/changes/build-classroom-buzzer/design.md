# Design

## Context

這是從零開始的新專案（動機見 proposal.md - Why）。限制條件：只需本機執行、不可洩漏金鑰、Guided Notes 不可用固定儲存格位置匯入匯出、要能在一台電腦上同時展示老師與至少 2 組學生畫面（Demo 影片需求）。OpenSpec 組與 SpecKit 組需產出功能一致的系統，因此行為以 specs 為準，技術選擇可以不同。

## Goals / Non-Goals

**Goals:**
- 一個指令就能在本機啟動，老師與學生都用瀏覽器操作。
- 搶答順序判定集中在伺服器，結果可重現、可測試。
- Guided Notes 匯入／匯出只依賴佔位符，任何遵守規範的試算表都能用。

**Non-Goals:**
- 不做對外部署、帳號系統、資料庫持久化（重啟即清空）。
- 不直接寫回雲端 Google Sheets（需要 OAuth 憑證），改為下載 `.xlsx` 再由老師匯入 Google Sheets。
- 不判斷答案對錯：搶答成功只看送出先後（公平模式另計）。
- 不支援多個活動同時進行（整個服務只有一場活動）。

## Decisions

### D1. 技術堆疊：Python + FastAPI + 原生 HTML/CSS/JS
- **選擇**：後端 FastAPI（內建 WebSocket、自動 API 文件），Uvicorn 執行；前端不使用框架，兩個靜態頁面 `teacher.html`、`student.html` 加上共用 JS。
- **理由**：與課程教學範例（Python）一致，組員好讀；不需 Node 打包流程；FastAPI 的 `TestClient` 可直接測 HTTP 與 WebSocket。
- **替代方案**：Flask + 輪詢（較簡單，但即時性差、伺服器負擔大）；Node.js + Socket.IO（需多學一套語言）。

### D2. 即時同步：WebSocket 推送「依角色過濾的完整快照」
- **選擇**：每個分頁建立一條 WebSocket `/ws?token=...`。任何狀態變更後，伺服器對每條連線重新產生**該身分可見的完整狀態快照**並推送；前端只負責把快照畫出來。
- **理由**：快照比「增量事件」簡單且不會漏事件；斷線重連後直接拿到最新快照（滿足 live-sync 的恢復需求）。可見性過濾集中在一個函式 `view_for(identity)`，容易測試「學生看不到別組」。
- **替代方案**：前端輪詢 REST（簡單但延遲與負擔較大）；Server-Sent Events（只能單向，送出答案仍需 REST，與目前做法差不多，但 FastAPI 的 WebSocket 測試支援較完整）。
- 寫入操作（匯入、開關、送出）一律走 REST，WebSocket 只負責推送，讓錯誤訊息能以 HTTP 狀態碼直接回給操作者。

### D3. 身分：伺服器發的隨機 token，存在分頁的 sessionStorage
- **選擇**：登入／加入成功後伺服器回傳 `secrets.token_urlsafe` 產生的 token，前端存 `sessionStorage`，之後放在 `Authorization: Bearer` 標頭與 WebSocket 參數中。
- **理由**：sessionStorage 以分頁為單位，同一瀏覽器的不同分頁可以是不同身分（Demo 需要），重新整理不會遺失。Cookie 會被所有分頁共用，做不到。
- 老師通行碼：讀取環境變數 `TEACHER_PASSCODE`；沒有就用 `secrets` 隨機產生 6 位數並印在終端機。比對使用 `secrets.compare_digest`。

### D4. 搶答狀態：單一 `Activity` 物件 + 一把鎖
- **選擇**：`activity.py` 內的純 Python 類別保存題目、組數、設定、階段與送出紀錄；所有修改都在 `asyncio.Lock` 內進行。每筆送出記錄遞增序號 `seq` 與 `time.monotonic()` 時間。
- **理由**：單一程序、記憶體保存即可滿足需求；序號保證同時送達時也有確定的先後；把邏輯與 Web 層分開，單元測試不需啟動伺服器。

### D5. 搶答成功判定為「純函式」，每次需要時重算
- **一般模式**：每個搶答單位依 `seq` 排序，第一筆成功。
- **公平模式**：
  1. 把有送出的搶答單位依「第一筆送出時間」排序。
  2. 依序處理每個單位：候選 = 送出時間 ≤ 第一筆時間 + 時間窗 的所有送出；選「目前已成功題數最少」者，同數取較早者；該組成功題數 +1。
- **理由**：結果只取決於送出紀錄，可重現、易測試；搶答中的結果標示為「暫定」，結束時即為最終結果。順位（rank）一律是送出先後，公平模式只影響誰成功。
- **替代方案**：送出時就決定成功者並固定（無法實作時間窗）；對已成功組別加延遲秒數（較難向學生解釋）。

### D6. Guided Notes：openpyxl 掃描佔位符
- 佔位符正規表示式：`\{\{\s*(\d+)(?:\s*-\s*(\d+))?\s*\}\}`。
- **匯入**：`openpyxl.load_workbook` 走訪所有工作表所有儲存格，只處理字串儲存格；記錄每個佔位符的（工作表、座標）。驗證規則見 specs/guided-notes。題目只保存題號與小題數，不保存敘述。
- **匯出**：保留原始檔案位元組；匯出時重新載入原檔，只對有成功答案的佔位符做字串替換後另存，因此其他儲存格與格式不變。重新掃描（而非使用記錄的座標）確保與匯入使用同一套規則。
- **Google Sheets 網址**：從網址取出試算表 ID，下載 `https://docs.google.com/spreadsheets/d/<ID>/export?format=xlsx`；HTTP 失敗或回傳不是 xlsx（未公開時會導到登入頁 HTML）時給出明確錯誤。使用標準函式庫 `urllib`，設 15 秒逾時、20 MB 上限。
- **替代方案**：Google Sheets API（需要服務帳號金鑰，違反「不洩漏金鑰」的精神且設定麻煩）；CSV 匯入（會失去多工作表與格式，無法寫回原檔）。

### D7. 專案結構

```
app/
  main.py          FastAPI 路由、WebSocket、啟動入口
  activity.py      活動狀態、送出規則、成功判定、角色視圖
  guided_notes.py  佔位符解析、驗證、寫回匯出
  sheets_url.py    Google Sheets 網址下載
  reporting.py     結果彙整與 CSV
  static/          index.html、teacher.html、student.html、app.css、common.js、teacher.js、student.js
samples/make_samples.py  產生範例 Guided Notes（單題、題組＋單題、換位置版本）
tests/             pytest：guided_notes、activity、reporting、api（含 WebSocket）
```

### D8. API 一覽

| 方法 | 路徑 | 角色 | 說明 |
|------|------|------|------|
| POST | `/api/teacher/login` | 任何人 | 通行碼換老師 token |
| POST | `/api/student/join` | 任何人 | 名字＋組別換學生 token |
| GET | `/api/me` | 已登入 | 取得自己身分 |
| GET | `/api/groups` | 任何人 | 目前組別清單（加入頁用） |
| POST | `/api/teacher/import/file` | 老師 | 上傳 xlsx |
| POST | `/api/teacher/import/url` | 老師 | Google Sheets 網址 |
| POST | `/api/teacher/settings` | 老師 | 組數、公平模式、時間窗 |
| POST | `/api/teacher/open` `/close` `/reset` | 老師 | 階段控制 |
| GET | `/api/teacher/export/guided-notes` | 老師 | 下載寫回答案的 xlsx |
| GET | `/api/teacher/export/csv` | 老師 | 下載結果 CSV |
| POST | `/api/student/submit` | 學生 | 送出一個搶答單位 |
| WS | `/ws?token=` | 已登入 | 推送角色視圖快照 |

下載類 API 也接受 `?token=`，讓瀏覽器可用一般連結下載。

## Risks / Trade-offs

- [伺服器重啟資料全失] → 文件明確說明；老師可隨時匯出 CSV／xlsx 保存。
- [Google Sheets 網址需公開檢視] → 頁面提示設定方式；無法公開時改用上傳 xlsx。
- [匯出不是直接改雲端原檔] → README 寫明「檔案 → 匯入 → 取代試算表」步驟；格式由 openpyxl 保留，但少數 Google 專屬功能（如核取方塊外觀）可能改變。
- [佔位符打錯（如 `{3}`）會被忽略] → 匯入後顯示題目清單與每題位置（工作表!儲存格），老師可核對題數。
- [每次變更推送完整快照，組數或題數很多時資料量變大] → 本作業規模（≤20 組、數十題）可忽略。
- [同一組多人同時送出] → 在鎖內檢查「本組已送出」，只有第一筆成功。

## Migration Plan

新專案，無需遷移。啟動：`pip install -r requirements.txt` → `python -m app.main`，瀏覽 `http://127.0.0.1:8000`。

## Open Questions

- 與 SpecKit 小組確認最終佔位符格式、預設組數與公平模式參數是否一致（不影響本設計架構，只需調整常數）。
