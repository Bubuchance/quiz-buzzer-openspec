# 03 Verify 驗證報告：build-classroom-buzzer

> 對應 OpenSpec 流程的 **Verify（驗證）**：逐條比對 spec、tasks 與實作。
> 指令：`/opsx:verify build-classroom-buzzer`（Codex 為 `$openspec-verify-change`）

## 總結

| 面向 | 結果 |
|------|------|
| Completeness：tasks | 23 / 23 完成 |
| Completeness：spec 覆蓋 | 5 個能力、25 條 Requirement 皆有實作 |
| Correctness：情境覆蓋 | 53 個 Scenario 中，51 個有自動化測試；2 個（同一瀏覽器模擬多角色、重新整理保留身分）以瀏覽器 E2E 驗證 |
| Coherence：與 design 一致 | 一致；實作期間的 3 處調整已回寫 design/proposal/tasks（見下方） |
| 自動化測試 | `python -m pytest`：54 passed |
| 瀏覽器 E2E | 老師＋2 組完整流程 16 項檢查全部通過，階段同步實測 67 ms（規格要求 < 2 秒） |

## Requirement 對照表

| 能力 | Requirement | 實作位置 | 測試 |
|------|-------------|----------|------|
| participant-access | 老師以通行碼登入 | `activity.py` `login_teacher`；`main.py` `generate_passcode` | `test_teacher_login`、`test_login_and_join`、`test_passcode_generated_when_not_configured`、`test_passcode_from_environment` |
| | 老師設定組數 | `activity.py` `update_settings` | `test_settings_ranges`、`test_settings_api` |
| | 學生選組加入 | `activity.py` `join_student` | `test_student_join_rules`、`test_login_and_join` |
| | 角色權限分離 | `main.py` `require_teacher`／`require_student` | `test_permissions` |
| | 分頁獨立身分 | `common.js` sessionStorage | 瀏覽器 E2E（3 分頁不同身分、重新整理保留） |
| guided-notes | 填空佔位符規範 | `guided_notes.py` `PLACEHOLDER_RE` | `test_placeholder_with_text_in_same_cell`、`test_group_and_spaces_inside_braces` |
| | 動態掃描匯入 | `parse_guided_notes` 走訪所有工作表 | `test_scans_all_sheets_any_position`、`test_samples_import_with_expected_counts` |
| | 匯入來源 | `main.py` import/file、import/url；`sheets_url.py` | `test_download_*`、`test_import_errors_and_url` |
| | 匯入驗證 | `parse_guided_notes` | `test_invalid_guided_notes`（7 種）、`test_not_an_xlsx`、`test_failed_import_keeps_old_questions` |
| | 匯入時機 | `activity.py` `import_notes` | `test_phase_flow`、`test_reimport_clears_submissions` |
| | 答案寫回匯出 | `guided_notes.py` `fill_answers` | `test_fill_answers_keeps_text_format_and_unanswered`、`test_full_flow_with_exports` |
| buzzer-activity | 活動階段 | `activity.py` `open`／`close` | `test_phase_flow` |
| | 重設活動 | `activity.py` `reset` | `test_reset_clears_submissions_keeps_questions` |
| | 以組別送出答案 | `activity.py` `submit` | `test_submit_rules` |
| | 每組每題只能送出一次 | `submit` 鎖內檢查 | `test_submit_rules`、`test_full_flow_with_exports` |
| | 最快送出者搶答成功 | `compute_winners` 一般模式 | `test_first_submission_wins` |
| | 公平模式 | `compute_winners` 公平模式 | `test_fair_mode_*`（3 個） |
| live-sync | 活動階段即時同步 | `main.py` `Hub.broadcast` | `test_websocket_sync`、E2E 67 ms |
| | 連線中斷後恢復 | `common.js` 自動重連；連線即送快照 | `test_reconnect_receives_latest_state` |
| | 老師即時檢視作答狀況 | `view_for` 老師分支 | `test_teacher_receives_new_submission_live` |
| | 結束前隱藏其他組作答 | `view_for` 學生分支 | `test_student_view_hides_other_groups_until_closed`、`test_websocket_sync` |
| | 結束後公開結果 | `view_for` CLOSED 分支 | 同上 |
| result-reporting | 結果檢視 | `reporting.py` `build_results`；`common.js` `renderResults` | `test_first_submission_wins`、E2E |
| | 各組成功題數統計 | `build_results` scoreboard | `test_scoreboard_sorted_by_wins` |
| | 結果 CSV 匯出 | `results_csv` | `test_csv_columns_and_group_rows`、`test_permissions` |

## 驗證過程中發現並修正的問題

| # | 問題 | 如何發現 | 修正 |
|---|------|----------|------|
| 1 | 真正啟動伺服器後瀏覽器 WebSocket 連不上（單元測試卻全過） | 瀏覽器 E2E | Uvicorn 預設不含 WebSocket 函式庫，`requirements.txt` 加入 `websockets`，並回寫 proposal、tasks |
| 2 | 題組在老師頁的位置清單重複顯示（`B5, B5`） | E2E 截圖檢查 | 前端去除重複位置 |
| 3 | 下載檔名的英文備用名稱是 `download` | E2E 下載檢查 | 改成 `<原檔名>-answers.xlsx`／`-results.csv`，中文檔名仍放在 `filename*` |
| 4 | 3 個 spec 情境沒有自動化測試（通行碼自動產生、斷線重連、老師即時收到答案） | 本次逐條對照 | 補上 4 個測試 |
| 5 | design 寫 `asyncio.Lock`、`view_for` 位置與實作不同 | 本次逐條對照 | 回寫 design.md（改為 `threading.RLock`、`reporting.py`） |

> 這就是作業要求「檢查 AI 生成的文件是否符合需求」的實例：#1 證明「只靠 AI 寫的單元測試不夠，還要實際操作」。

## 尚未驗證／需要組員完成

- **人工驗證**：作業規定除 AI 自動驗證外須人工驗證，請組員依 `docs/04-人工驗證清單.md` 親自操作並勾選。
- **真正的 Google Sheets 網址匯入**：開發環境無法連到 Google，網址下載以模擬資料測試；請用老師給的範本實際試一次。
- **老師提供的範本**：作業 PDF 中的「單題範本」「題組＋單題範本」連結我們拿不到，需確認範本加上佔位符後可正常匯入。
