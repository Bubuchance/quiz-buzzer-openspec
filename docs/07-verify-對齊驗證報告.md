# 07 Verify 驗證報告：align-with-speckit

> 指令：`/opsx:verify align-with-speckit`（Codex 為 `$openspec-verify-change`）

## 總結

| 面向 | 結果 |
|------|------|
| Completeness：tasks | 15 / 15 完成 |
| Completeness：spec 覆蓋 | 新增／修改 15 條 Requirement（MODIFIED 6、ADDED 9）皆有實作；REMOVED 3 條（舊佔位符規範、舊匯入驗證、舊時間窗公平模式、舊 CSV）程式中已無殘留 |
| Correctness：情境覆蓋 | 41 個 Scenario 全部有自動化測試；倒數、標記、進度另以瀏覽器 E2E 驗證 |
| Coherence：與 design 一致 | 一致（D1～D9 皆對應到程式） |
| 自動化測試 | `python -m pytest`：74 passed |
| 瀏覽器 E2E | 老師＋2 組：匯入 → 設定時限 8 秒與公平模式 → 搶答 → 進度 2/5 → 倒數到 0 自動結束（三個頁面同步）→ 標記對錯 → 計分板 → 匯出 xlsx／CSV，12 項檢查全部通過 |

## 移除項目確認（REMOVED）

| 移除的需求 | 確認方式 |
|------------|----------|
| 填空佔位符規範（`{{n}}`） | `grep "{{" app/` 無結果；解析只認「題號」「作答」標題 |
| 匯入驗證（舊） | 由「學習單格式驗證」取代，`test_invalid_sheets` 9 種錯誤 |
| 公平模式（時間窗） | `fair_window` 已從程式、API、前端移除，改為 `fair_delay` |
| 結果 CSV 匯出（7 欄） | `CSV_HEADER` 為 6 欄，`test_csv_columns_and_rows` 驗證 |

## Requirement 對照表

| 能力 | Requirement | 實作 | 測試 |
|------|-------------|------|------|
| guided-notes | 學習單欄位標題與題組標示（ADDED） | `guided_notes.py` `_find_header`、`_parse` | `test_header_moved_and_column_order_changed`、`test_group_across_rows_full_and_half_width`、`test_non_question_rows_skipped`、`test_number_formats` |
| | 學習單格式驗證（ADDED） | `_parse` 驗證段 | `test_invalid_sheets`、`test_no_header`、`test_not_an_xlsx` |
| | 動態掃描匯入（MODIFIED） | 第一個含標題列的工作表 | `test_first_sheet_with_header_is_used`、`test_samples_import_with_expected_counts` |
| | 匯入時機（MODIFIED） | `activity.import_notes` 清除作答與標記 | `test_reset_and_reimport_clear_submissions_and_marks` |
| | 答案寫回匯出（MODIFIED） | `fill_answers` | `test_fill_answers_singles_groups_and_blanks`、`test_fill_answers_on_moved_sample`、`test_full_flow_with_exports` |
| buzzer-activity | 活動階段（MODIFIED） | `PHASE_LABELS` | `test_phase_labels_three_stages`、`test_phase_flow` |
| | 重設活動（MODIFIED） | `activity.reset` | `test_reset_and_reimport_clear_submissions_and_marks` |
| | 以組別送出答案（MODIFIED） | `activity.submit` | `test_submit_rules` |
| | 公平順位延遲機制（ADDED） | `prior_wins`、`effective_time`、`rank_submissions` | `test_fair_mode_delays_group_with_more_wins`、`test_fair_mode_still_faster_after_delay`、`test_prior_wins_counted_at_receive_time`、`test_settings_ranges` |
| | 搶答倒數計時（ADDED） | `open`／`expire`／`expire_if_due`；`main.py` `expire_later` | `test_countdown_expires`、`test_countdown_timer_callback`、`test_manual_close_cancels_old_round`、`test_countdown_auto_close_broadcasts` |
| result-reporting | 各組成功題數統計 → 計分板（MODIFIED） | `build_results` scoreboard | `test_marking_rules_and_scoreboard` |
| | 活動結果 CSV 匯出（ADDED） | `results_csv` | `test_csv_columns_and_rows`、`test_permissions` |
| | 老師標記對錯（ADDED） | `activity.mark`；`POST /api/teacher/mark` | `test_marking_rules_and_scoreboard`、`test_mark_api_and_permissions` |
| live-sync | 學生端作答進度提示（ADDED） | `view_for` `progress` | `test_student_view_hides_other_groups_until_closed`、`test_student_progress_in_state` |
| participant-access | 角色權限分離（MODIFIED） | `require_teacher` | `test_permissions`、`test_mark_api_and_permissions` |

## 驗證過程中發現並修正的問題

| # | 問題 | 修正 |
|---|------|------|
| 1 | `openspec validate` 拒絕：MODIFIED 不可刪掉舊情境 | 行為根本改變的需求改用 REMOVED（附原因與遷移方式）＋ ADDED 新需求 |
| 2 | 老師頁同時顯示「對」標籤與亮起的「對」按鈕，資訊重複 | 老師可編輯時只顯示按鈕 |
| 3 | `openspec/config.yaml` 仍寫著舊的 `{{n}}` 規則 | 改為欄位標題規則，並指向對齊清單 |

## 尚待 SpecKit 組確認

見 `docs/speckit/feature-alignment.md` 第 3 節。若對方選擇不同的預設值（例如延遲量），只需修改 `app/activity.py` 頂端的常數與對應測試。
