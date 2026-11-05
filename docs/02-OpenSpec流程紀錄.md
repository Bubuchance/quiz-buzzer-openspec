# 02 OpenSpec 流程紀錄

本專案依照課程教材的 OpenSpec 流程完成，只使用**一個 change**：`build-classroom-buzzer`。
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
