# 02 OpenSpec 流程紀錄

本專案依照課程教材的 OpenSpec 流程完成，共三個 change：

1. `build-classroom-buzzer`：從零建立系統（main 分支）。
2. `align-with-speckit`：依 SpecKit 組的對齊清單修改與新增功能（`feature/align-with-speckit` 分支，以 PR 合併）。這正是老師流程圖中「已歸檔後要新增功能，就回 explore 開新的 Change」。
3. `connect-google-sheets`：依 11-17 課程公告，改為以 Google Sheets API 直接讀寫雲端試算表（同一分支，隨 PR #1 合併）。
每一步都有對應的 git commit，可在 GitHub 的 commit 歷史中看到流程順序。

```
安裝 → init → explore → propose → apply → verify → sync → archive → 固化 config.yaml
```

| 步驟 | 指令（Claude Code／Codex） | 產出 | 對應 commit |
|------|------------------|------|------|
| 01 安裝 | `npm install -g @fission-ai/openspec@latest` | OpenSpec CLI 1.16.0 | — |
| 02 初始化 | `openspec init --tools codex,claude --language zh-TW --profile core` | `.agents/`、`.claude/`、`openspec/` | `chore: openspec init + propose` |
| 02b 設定 workflow | `openspec config profile`（選 explore、propose、apply、archive、verify、sync、update、bulk-archive）→ `openspec update` | 8 個 skill | 同上 |
| 03 Explore | `/opsx:explore`（Codex：`$openspec-explore`） | `docs/01-explore-需求釐清.md`（討論紀錄，不建 artifacts） | 同上 |
| 04 Propose | `/opsx:propose build-classroom-buzzer` | proposal.md、design.md、tasks.md、5 份 spec | 同上 |
| 05 Apply | `/opsx:apply build-classroom-buzzer` | `app/`、`tests/`、`samples/`、README，tasks 全部 `[x]` | `feat: apply ...` |
| 06 Verify | `/opsx:verify build-classroom-buzzer` | `docs/03-verify-驗證報告.md`、補測試 | `test: verify ...` |
| 07 Sync | `/opsx:sync build-classroom-buzzer` | `openspec/specs/` 5 份主規格 | `docs: sync ...` |
| 08 Archive | `/opsx:archive build-classroom-buzzer` | `openspec/changes/archive/2026-11-05-build-classroom-buzzer/` | `chore: archive ...` |
| 09 固化規則 | 「讀取 openspec/config.yaml，並協助我填寫我的專案、技術堆疊與慣例」 | `openspec/config.yaml` | 同上 |

## 每一步的提示詞（給組員用 Codex 重現或延伸）

### 03 Explore
見 `docs/01-explore-需求釐清.md` 開頭。

### 04 Propose
```text
/openspec propose build-classroom-buzzer
請依照剛才 Explore 確認的全部規則與合理預設，從零規劃「課堂搶答系統」。能力拆成 participant-access、
guided-notes、buzzer-activity、live-sync、result-reporting。涵蓋老師通行碼／學生選組、Guided Notes
佔位符匯入（xlsx 或公開 Google Sheets 網址）與寫回匯出、開啟／結束／重設搶答、以組別送出、每組每題一次、
最快者成功、結束前隱藏他組作答、WebSocket 即時同步、結果檢視與 CSV、題組與公平模式。
後端用 Python FastAPI，頁面用 HTML/CSS/JS；先完成提案，暫不實作。
```

### 05 Apply
```text
/openspec apply build-classroom-buzzer
請依照這個 change 的 proposal、design、spec 與 tasks 完成系統並逐項勾選 tasks。每個任務群組完成時
執行 pytest；前端完成後實際啟動伺服器，用瀏覽器以老師＋2 組跑完整流程，並更新 README。
```

### 06 Verify
```text
/openspec verify build-classroom-buzzer
請對照 spec 與 tasks 檢查實作，逐條列出 Requirement 與 Scenario 的實作位置與測試；
有沒測到的情境就補測試，文件與程式不一致就修正後重驗。
```

### 07 Sync／08 Archive
```text
/openspec sync build-classroom-buzzer
/openspec archive build-classroom-buzzer
```

## 之後要新增功能怎麼做？

依老師的流程圖：已歸檔後若要新增功能，回到 Explore **開新的 change**（例如 `add-countdown-timer`），
每個 change 代表系統當下新增了什麼。新的 change 的 spec 會以 `## ADDED`／`## MODIFIED` 對現有主規格做增修。

## 為什麼這樣拆能力（capability）？

依 OpenSpec 規則，能力要以「長期存在的系統行為」命名，而不是這次的工作項目：
- `participant-access`：誰能進來、能做什麼
- `guided-notes`：跟學習單檔案有關的一切（格式、匯入、匯出）
- `buzzer-activity`：搶答本身的規則
- `live-sync`：誰在什麼時候看到什麼
- `result-reporting`：結果與報表

以後若加「倒數計時」會修改 `buzzer-activity`，加「匯出 PDF」會修改 `result-reporting`，邊界清楚。

## 第二個 change：align-with-speckit

| 步驟 | 產出 | 對應 commit |
|------|------|------|
| 開分支 | `git checkout -b feature/align-with-speckit` | — |
| Explore | `docs/06-explore-與SpecKit對齊.md`（差異比對、待確認項目建議） | `docs: explore + propose align-with-speckit` |
| Propose | proposal、design、tasks；delta spec 使用 MODIFIED／REMOVED／ADDED | 同上 |
| Apply | 學習單改欄位標題、公平延遲公式、倒數計時、標記對錯、作答進度、CSV 6 欄 | `feat: apply align-with-speckit ...` |
| Verify | `docs/07-verify-對齊驗證報告.md` | `test: verify align-with-speckit` |
| Sync | 主規格合併（例如 buzzer-activity：刪 1、改 3、增 2） | `docs: sync align-with-speckit ...` |
| Archive | `openspec/changes/archive/2026-11-17-align-with-speckit/` | `chore: archive align-with-speckit` |

學到的事：行為「根本改變」的需求不能用 MODIFIED 直接改寫（OpenSpec 會拒絕刪掉舊情境），要用 REMOVED 寫明原因與遷移方式，再 ADDED 新需求。這讓規格的變更歷史可追溯。

### Explore 提示詞
```text
/openspec explore
請比對 docs/speckit/features.md、docs/speckit/feature-alignment-原始版.md 與目前 openspec/specs/ 的主規格，
列出兩組行為不一致之處、需要新增的功能，以及「待雙方確認」項目的建議做法。本次只討論，不寫程式。
```
### Propose 提示詞
```text
/openspec propose align-with-speckit
依剛才的比對結果修改系統：學習單改依「題號」「作答」欄位標題定位、題組用（1）（2）；階段統一為
準備中／搶答中／已結束；公平模式改為「有效時間 = 收到時間 + 已成功題數 × 延遲量」；CSV 改為 6 欄；
新增倒數計時、老師標記對錯與計分板、學生端作答進度。行為改變的需求用 REMOVED + ADDED。
```

## 第三個 change：connect-google-sheets

起因：課程公告「系統需直接串接自己雲端線上的 Google Sheets 進行讀寫，而非下載成 .xlsx 檔在本地端離線處理」。

| 步驟 | 產出 |
|------|------|
| Explore | `docs/08-explore-串接GoogleSheets.md`（違反之處、授權方式比較：服務帳號 vs OAuth vs Apps Script） |
| Propose | delta spec：REMOVED「匯入來源」「答案寫回匯出」，ADDED「從雲端 Google Sheets 匯入」「寫回雲端 Google Sheets」「Google Sheets 授權設定」，MODIFIED「學習單格式驗證」 |
| Apply | `app/google_sheets.py`（gspread、服務帳號）、解析改吃值格線、寫回 API、老師頁服務帳號提示 |
| Verify | `docs/09-verify-GoogleSheets串接驗證報告.md` |
| Sync／Archive | `openspec/changes/archive/<日期>-connect-google-sheets/` |
