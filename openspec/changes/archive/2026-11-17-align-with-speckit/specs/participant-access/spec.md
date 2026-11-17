# Spec Delta

## MODIFIED Requirements

### Requirement: 角色權限分離
系統 MUST 拒絕非老師身分執行老師操作（匯入、開啟、結束、重設、設定、匯出、標記對錯），也 MUST 拒絕非學生身分送出答案。

#### Scenario: 學生嘗試開啟搶答
- **WHEN** 學生身分呼叫開啟搶答
- **THEN** 系統回應權限不足，活動階段不變

#### Scenario: 學生嘗試標記對錯
- **WHEN** 學生身分呼叫標記對錯
- **THEN** 系統回應權限不足，標記不變

#### Scenario: 未登入送出答案
- **WHEN** 沒有身分的請求送出答案
- **THEN** 系統拒絕，且不記錄任何答案
