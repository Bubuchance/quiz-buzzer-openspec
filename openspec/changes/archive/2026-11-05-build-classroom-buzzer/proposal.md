# Proposal

## Why

老師目前讓各組把 Guided Notes（填空式學習單）的答案寫到黑板上搶答，收講義、上台書寫、判斷誰先寫都很花時間。我們要把這個活動搬到線上：老師匯入題目、開關搶答，學生以組別為單位線上送出，系統自動判定最快的組別，並把成功答案寫回原本的 Guided Notes。

## What Changes

- 新增老師與學生兩種角色：老師以通行碼登入；學生輸入名字並選擇組別加入。
- 新增 Guided Notes 匯入：上傳 `.xlsx` 或貼上公開檢視的 Google Sheets 網址，系統掃描所有工作表的填空佔位符（單題 `{{n}}`、題組 `{{n-k}}`）建立題目清單，題數與 Guided Notes 一致，不使用固定儲存格位置。
- 新增搶答活動：老師開啟／結束搶答；學生在搶答中以組別送出每題（或整個題組）的答案，每組每題只能送一次；每題最快送出的組別為搶答成功。
- 新增作答可見性規則：搶答結束前學生只能看到自己組的送出狀況；老師可即時看到所有組的作答與暫定結果；結束後所有人可看結果。
- 新增活動階段即時同步：所有已開啟的頁面在階段或題目變動時自動更新，不需重新整理。
- 新增 Guided Notes 匯出：把搶答成功的答案寫入原本的填空格，下載為保留原格式的 `.xlsx`。
- 額外功能：題組匯入（題組須同時送出）、活動結果 CSV 匯出（題號、小題、組別、答案、順位、是否成功）、公平模式（時間窗內成功題數較少的組別優先）。

## Capabilities

### New Capabilities

- `participant-access`: 老師與學生的身分進入方式、組別設定與角色權限。
- `guided-notes`: Guided Notes 的佔位符規範、題目匯入（檔案／網址）與答案寫回匯出。
- `buzzer-activity`: 活動階段（未匯入、等待開始、搶答中、已結束）、答案送出規則、搶答成功判定與公平模式。
- `live-sync`: 活動階段、題目與作答狀態對所有使用者的即時同步，以及依角色過濾可見資訊。
- `result-reporting`: 老師與學生檢視搶答結果，以及結果 CSV 匯出。

### Modified Capabilities

（無，這是新專案）

## Impact

- 新增 Python 後端（FastAPI + WebSocket）與 HTML/CSS/JavaScript 前端頁面（老師頁、學生頁）。
- 新增相依套件：`fastapi`、`uvicorn`、`websockets`（Uvicorn 的 WebSocket 支援）、`openpyxl`、`python-multipart`；測試使用 `pytest`、`httpx`。
- 新增 `samples/` 範例 Guided Notes 產生腳本，供測試與 Demo 使用。
- 不需要任何 Google API 金鑰；老師通行碼由環境變數提供或啟動時隨機產生，不寫進 repo。
- 只在本機執行（`127.0.0.1`），資料只存在記憶體。
