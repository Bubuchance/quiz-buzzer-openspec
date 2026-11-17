# Spec Delta

## ADDED Requirements

### Requirement: 學生端作答進度提示
系統 SHALL 在學生頁顯示「本組已送出 N / 總題數」，N 為本組已送出的搶答單位數；此提示 MUST NOT 包含其他組別的任何資訊。

#### Scenario: 顯示本組進度
- **WHEN** 共 5 題，第 1 組已送出第 1、3 題
- **THEN** 第 1 組所有成員的頁面顯示「本組已送出 2 / 5 題」

#### Scenario: 不受他組影響
- **WHEN** 第 2 組送出第 2 題
- **THEN** 第 1 組頁面的進度數字不變
