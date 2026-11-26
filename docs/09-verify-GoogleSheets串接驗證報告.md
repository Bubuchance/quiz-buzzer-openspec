# 09 Verify 驗證報告：connect-google-sheets

> 指令：`/opsx:verify connect-google-sheets`

## 總結

| 面向 | 結果 |
|------|------|
| Completeness：tasks | 9 / 9 完成 |
| Completeness：spec 覆蓋 | MODIFIED 1、ADDED 3 條皆有實作；REMOVED 2 條（xlsx 匯入來源、xlsx 匯出）程式中已無殘留：`sheets_url.py` 已刪除，`/api/teacher/import/file`、`/api/teacher/export/guided-notes` 已移除 |
| Correctness：情境覆蓋 | 15 個 Scenario 皆有自動化測試（以假的 Google Sheets 閘道） |
| Coherence：與 design 一致 | D1～D7 皆對應到程式 |
| 自動化測試 | `python -m pytest`：94 passed |
| 瀏覽器 E2E（假閘道） | 服務帳號 email 顯示、錯誤網址提示、從（模擬）雲端匯入老師題組範本版面 4 題、搶答、結束後寫回、雲端格線內容正確（「（1）CPU」「（2）作業系統」「0」、無人作答為空白） |

## Requirement 對照表

| Requirement | 實作 | 測試 |
|-------------|------|------|
| 學習單格式驗證（MODIFIED，移除 .xlsx 條件） | `guided_notes.parse_spreadsheet` | `test_invalid_sheets`、`test_no_header`、`test_import_errors` |
| 從雲端 Google Sheets 匯入（ADDED） | `google_sheets.spreadsheet_id`、`GoogleSheetsGateway.read`、`POST /api/teacher/import/url` | `test_spreadsheet_id_from_url_and_bare_id`、`test_bad_spreadsheet_ids`、`test_read_returns_all_sheets`、`test_import_errors` |
| 寫回雲端 Google Sheets（ADDED） | `guided_notes.build_writes`、`activity.prepare_writeback`、`GoogleSheetsGateway.write`（RAW）、`POST /api/teacher/export/google-sheets` | `test_build_writes_singles_groups_and_blanks`、`test_written_sheet_can_be_reimported_and_rewritten`、`test_writeback_updates`、`test_writeback_rejects_changed_structure`、`test_write_uses_raw_batch_update`、`test_writeback_rules`、`test_full_flow_with_exports` |
| Google Sheets 授權設定（ADDED） | `GoogleSheetsGateway.status`、`error_for_status`、`GET /api/teacher/sheets-status`、老師頁狀態區塊、`.gitignore` | `test_missing_credentials`、`test_credentials_from_environment`、`test_error_messages`、`test_read_error_translation`、`test_gateway_unconfigured_message`、`test_sheets_status` |

## 尚未驗證（需要組員在自己電腦完成）

開發環境無法連到 Google API，也沒有服務帳號金鑰，所以**真正連線到 Google Sheets 的讀寫**只用假閘道驗證了呼叫方式（gspread 的 `open_by_key`、`get_all_values`、`batch_update(..., value_input_option="RAW")`）。請依 `docs/04-人工驗證清單.md` 的「Guided Notes」與「匯出」段落，用老師範本的副本實際測一次。
