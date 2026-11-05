# Tasks

## 1. 專案骨架與相依套件

- [ ] 1.1 建立 `app/`、`app/static/`、`tests/`、`samples/` 目錄與 `app/__init__.py`，並確認 `python -c "import app"` 成功
- [ ] 1.2 建立 `requirements.txt`（fastapi、uvicorn、openpyxl、python-multipart、pytest、httpx）與 `.gitignore`（排除 `.venv`、`__pycache__`、`.env`、匯出檔），並確認 `pip install -r requirements.txt` 成功

## 2. Guided Notes 匯入與匯出（guided-notes）

- [ ] 2.1 在 `app/guided_notes.py` 實作佔位符掃描：走訪所有工作表與儲存格，辨識 `{{n}}` 與 `{{n-k}}`（允許空白、可與文字同格），並以單元測試驗證同格文字、題組、多工作表情境
- [ ] 2.2 實作匯入驗證（非 xlsx、無佔位符、重複、單題與題組混用、題號跳號、小題跳號），每種錯誤皆有中文訊息，並以單元測試逐一驗證
- [ ] 2.3 實作答案寫回：重新載入原檔，只替換有成功答案的佔位符、保留其他文字與格式、無人成功的保留佔位符，並以單元測試驗證單題、題組與未作答情境
- [ ] 2.4 在 `app/sheets_url.py` 實作 Google Sheets 網址解析與下載（逾時、大小上限、非 xlsx 回應的錯誤），並以模擬下載的單元測試驗證成功與失敗情境
- [ ] 2.5 建立 `samples/make_samples.py` 產生「單題範例」「題組＋單題範例」「換位置範例」三份 xlsx，並以測試確認三份皆可匯入且題數正確

## 3. 搶答活動核心（buzzer-activity）

- [ ] 3.1 在 `app/activity.py` 實作活動階段（未匯入／等待開始／搶答中／已結束）與開啟、結束、重設、匯入時機規則，並以單元測試驗證合法與不合法的轉換
- [ ] 3.2 實作組數、公平模式、時間窗設定與範圍檢查（搶答中不可修改），並以單元測試驗證
- [ ] 3.3 實作答案送出：非空檢查、題組須填完、每組每單位只收第一次、非搶答中拒絕、記錄序號與時間，並以單元測試驗證
- [ ] 3.4 實作成功判定純函式（一般模式先送先贏；公平模式時間窗＋成功題數少者優先）與順位計算，並以單元測試驗證 spec 中的公平模式情境

## 4. 身分與角色視圖（participant-access、live-sync）

- [ ] 4.1 實作老師通行碼（環境變數或隨機產生並只印在終端機、`compare_digest` 比對）與學生加入（名字驗證、組別存在），回傳隨機 token，並以單元測試驗證
- [ ] 4.2 實作 `view_for(identity)`：老師看到全部與暫定結果；學生在結束前只看到本組送出；結束後所有人看到完整結果，並以單元測試確認學生視圖不含其他組任何資訊

## 5. 結果彙整與 CSV（result-reporting）

- [ ] 5.1 在 `app/reporting.py` 實作每題結果、各組成功題數排序與 CSV（UTF-8 BOM、題組展開為多列、欄位依 spec），並以單元測試驗證欄位與列數

## 6. Web API 與即時推送

- [ ] 6.1 在 `app/main.py` 建立 FastAPI 應用、靜態檔案、design 中列出的 REST API 與權限檢查，並以 `TestClient` 測試每個 API 的成功與權限不足情境
- [ ] 6.2 實作 WebSocket `/ws`：連線時送出角色視圖快照、每次狀態變更推送給所有連線、無效 token 拒絕，並以 `TestClient` WebSocket 測試驗證老師開啟搶答後學生收到「搶答中」
- [ ] 6.3 實作 `python -m app.main` 啟動入口（只綁定 127.0.0.1、印出網址與老師通行碼），並確認啟動後首頁回應 200

## 7. 前端頁面

- [ ] 7.1 建立 `index.html`（老師登入、學生選組加入）與共用 `common.js`（token 儲存於 sessionStorage、API 呼叫、WebSocket 自動重連），並在瀏覽器確認登入／加入後導向正確頁面
- [ ] 7.2 建立 `teacher.html`／`teacher.js`：匯入（檔案／網址）、題目清單與位置、設定、開啟／結束／重設、即時作答表、結果與匯出按鈕，並在瀏覽器確認操作即時反映
- [ ] 7.3 建立 `student.html`／`student.js`：階段顯示、單題與題組作答欄、本組已送出狀態、結束後結果，並在瀏覽器確認結束前看不到別組
- [ ] 7.4 建立 `app.css`，確認老師頁與學生頁在桌面與手機寬度皆可正常操作

## 8. 文件與整合驗證

- [ ] 8.1 撰寫 `README.md`：安裝、啟動、Guided Notes 佔位符規範、Google Sheets 匯入匯出步驟、Demo 流程、測試指令，並依 README 指令從頭執行一次確認可行
- [ ] 8.2 執行 `pytest` 全部通過，並以瀏覽器完成一次完整流程（老師＋2 組：匯入 → 開啟 → 搶答 → 結束 → 匯出 xlsx 與 CSV），確認符合所有 spec 情境

## Workflow follow-up

- 執行 `/opsx:verify build-classroom-buzzer` 比對 spec、tasks 與實作。
- 驗證通過後執行 `/opsx:sync build-classroom-buzzer` 把 specs 合併到 `openspec/specs/`。
- 執行 `/opsx:archive build-classroom-buzzer` 將 change 封存。
- 人工驗證：組員親自操作一次完整流程並記錄結果（作業要求 AI 驗證之外須人工驗證）。
