# Spec Delta

## MODIFIED Requirements

### Requirement: 學習單格式驗證
系統 MUST 在下列情況拒絕匯入並說明原因，且保留原有題目：找不到同時含「題號」「作答」的標題列、標題列下沒有任何題目、題號重複、題號不是從 1 開始連續、題組小題號不是從 1 開始連續、題號欄為空的（k）列前面沒有所屬題組。

#### Scenario: 找不到標題
- **WHEN** 老師匯入沒有「題號」「作答」標題的試算表
- **THEN** 系統顯示找不到欄位標題並保留原題目

#### Scenario: 題號跳號
- **WHEN** 題號欄只有 1、2、4
- **THEN** 系統顯示缺少第 3 題，不匯入

#### Scenario: 題號重複
- **WHEN** 題號 2 出現在兩列
- **THEN** 系統顯示第 2 題重複，不匯入

## REMOVED Requirements

### Requirement: 匯入來源
**Reason**: 課程公告要求直接串接雲端 Google Sheets 讀寫，不可下載成 .xlsx 離線處理；上傳 xlsx 與公開網址下載 xlsx 皆屬離線處理。
**Migration**: 把學習單共用給系統的服務帳號後，貼上試算表網址匯入；見「從雲端 Google Sheets 匯入」。

### Requirement: 答案寫回匯出
**Reason**: 下載 xlsx 再手動匯入不是直接寫回雲端，違反課程公告。
**Migration**: 搶答結束後按「寫回 Google Sheets」，系統直接修改雲端試算表；見「寫回雲端 Google Sheets」。

## ADDED Requirements

### Requirement: 從雲端 Google Sheets 匯入
系統 SHALL 讓老師在非搶答中貼上自己 Google Sheets 的網址或試算表 ID，透過 Google Sheets API 即時讀取該試算表所有工作表的儲存格內容，再依欄位標題規則匯入題目；系統 MUST NOT 要求下載或上傳 .xlsx 檔案。

#### Scenario: 貼上網址匯入
- **WHEN** 老師貼上已共用給系統服務帳號的 Google Sheets 網址
- **THEN** 系統直接讀取雲端內容並顯示題目清單與每題作答格位置

#### Scenario: 網址格式錯誤
- **WHEN** 老師貼上的不是 Google Sheets 網址，也不是試算表 ID
- **THEN** 系統顯示請貼上 Google Sheets 網址，題目不變

#### Scenario: 找不到試算表
- **WHEN** 網址中的試算表不存在
- **THEN** 系統顯示找不到試算表，題目不變

### Requirement: 寫回雲端 Google Sheets
系統 SHALL 讓老師在搶答「已結束」後，把結果直接寫入匯入時的雲端試算表：單題作答格寫入成功答案、無人成功則寫入空白；題組小題格寫成「（k）答案」、無人成功則只保留「（k）」。寫入一律為純文字，不改動其他儲存格。寫回前系統 MUST 重新讀取試算表，題號或題組小題數與匯入時不同就拒絕寫回。

#### Scenario: 寫入單題與題組
- **WHEN** 已結束，第 1 題由第 2 組以「CPU」成功，題組第 2 題由第 1 組以「演算法」「堆疊」成功，老師按寫回
- **THEN** 雲端試算表第 1 題作答格為「CPU」，第 2 題兩格分別為「（1）演算法」「（2）堆疊」

#### Scenario: 無人成功的題目
- **WHEN** 第 3 題無人搶答，老師寫回
- **THEN** 第 3 題作答格為空白

#### Scenario: 搶答未結束
- **WHEN** 搶答中或準備中老師按寫回
- **THEN** 系統拒絕並提示搶答結束後才能寫回

#### Scenario: 匯入後試算表被改動
- **WHEN** 匯入後有人在試算表刪除了一題，老師按寫回
- **THEN** 系統拒絕寫回並提示重新匯入

#### Scenario: 寫回後可再次匯入
- **WHEN** 老師對已寫回答案的試算表再次匯入
- **THEN** 系統辨識出與原本相同的題數與題組

#### Scenario: 答案不會變成公式
- **WHEN** 成功答案為「=1+1」
- **THEN** 雲端儲存格顯示文字「=1+1」而不是計算結果

### Requirement: Google Sheets 授權設定
系統 SHALL 使用 Google 服務帳號存取試算表：金鑰檔放在本機、路徑由環境設定指定，MUST NOT 存在於 repo。老師頁 SHALL 顯示服務帳號 email 與是否已設定；尚未設定、沒有權限、連線失敗時，系統 SHALL 顯示可理解的中文說明。

#### Scenario: 顯示服務帳號
- **WHEN** 金鑰已設定，老師打開控制台
- **THEN** 頁面顯示「請把試算表共用給 <服務帳號 email>（編輯者）」

#### Scenario: 尚未設定金鑰
- **WHEN** 金鑰檔不存在時老師匯入
- **THEN** 系統顯示尚未設定 Google 服務帳號並指出設定說明

#### Scenario: 沒有共用權限
- **WHEN** 試算表沒有共用給服務帳號
- **THEN** 系統顯示請把試算表共用給該服務帳號 email（編輯者）
