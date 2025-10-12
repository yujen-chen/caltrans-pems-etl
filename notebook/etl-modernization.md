# ETL Modernization Plan
# ETL 現代化規劃

**Branch**: `feature/etl-modernization`
**Created**: 2025-10-12
**Goal**: 整合 cloud-test/ step 1-5 的學習成果，建構完整的現代化 ETL 架構

---

## 🎯 總體目標

將目前的基礎下載/處理架構升級為完整的雲端 ETL pipeline：

```
目前架構:
下載 (handler.py) → 本地處理 (data_processor.py) → 本地 Parquet

目標架構:
下載 → 處理 → R2 上傳 → DuckDB 查詢 → dbt 轉換 → Airflow 編排 → Dashboard
```

---

## 📋 Phase 概覽

| Phase | 目標 | 對應 cloud-test | 狀態 | 預估時間 |
|-------|------|----------------|------|---------|
| **Phase 0** | 審查現有下載程式碼 | - | 🔄 進行中 | 1 小時 |
| **Phase 1** | R2 上傳功能 | step 2-3 | ⏳ 待開始 | 2-3 小時 |
| **Phase 2** | DuckDB 整合 | step 1-2 | ⏳ 待開始 | 2-3 小時 |
| **Phase 3** | dbt 轉換 | step 4 | ⏳ 待開始 | 3-4 小時 |
| **Phase 4** | Airflow 編排 | step 3 | ⏳ 待開始 | 3-4 小時 |
| **Phase 5** | 整合測試 | step 5 | ⏳ 待開始 | 2-3 小時 |

**總預估**: 13-18 小時

---

## 🔍 Phase 0: 程式碼審查 (目前階段)

### 目標
- 審查 `src/pems/core/handler.py` 下載邏輯
- 識別可改進之處與整合點
- 規劃 R2 上傳的整合方式

### 審查重點
1. 下載流程的穩定性與錯誤處理
2. 檔案儲存邏輯（為 R2 上傳做準備）
3. 進度追蹤與日誌記錄
4. 可重用性與模組化程度

### 輸出
- [ ] 下載程式碼審查報告
- [ ] 改進建議清單
- [ ] R2 整合點識別

---

## 💾 R2 儲存策略規劃

### 專案儲存需求分析

#### 資料量估算
```
Raw Data:
- 每月: 50 MB
- 100 個月: 50 MB × 100 = 5,000 MB = 5 GB

Processed Parquet:
- 每年: 20 MB
- 100 個月 (≈8.33 年): 20 MB × 8.33 = 166.6 MB ≈ 0.17 GB

dbt Marts (預估):
- ≈ 50 MB = 0.05 GB

總計: 5 + 0.17 + 0.05 = 5.22 GB
```

**結論**: ✅ **R2 免費方案 (10 GB) 足夠使用**，還剩約 4.78 GB 空間

---

### 推薦上傳策略：智慧混合策略

#### 核心原則
1. ✅ **Processed Parquet 必定上傳**（主要使用資料）
2. 🔄 **Raw 滾動備份最近 12 個月**（可重新處理）
3. ♻️ **本地 Raw 保留 30 天後刪除**（節省空間）

#### 詳細規則表

| 資料類型 | 上傳 R2？ | R2 路徑 | 本地保留 | 空間占用 |
|---------|----------|---------|---------|---------|
| **Processed Parquet** | ✅ 必定上傳 | `s3://pems/processed/YYYY/` | 永久 | 0.17 GB |
| **Raw (最近12月)** | 🔄 滾動上傳 | `s3://pems/raw-rolling/YYYY-MM/` | 30 天 | 0.6 GB |
| **Raw (舊資料)** | ❌ 不上傳 | - | 刪除 | 0 GB |
| **dbt Marts** | ✅ 上傳 | `s3://pems/marts/` | 永久 | 0.05 GB |

#### R2 Bucket 結構

```
s3://pems-processed/
├── processed/                  # 主要使用資料（Parquet）
│   ├── 2019/
│   │   └── 2019_station_hour_processed.parquet
│   ├── 2020/
│   ├── ...
│   └── 2027/
│
├── raw-rolling/                # 滾動備份（最近12月）
│   ├── 2026-11/
│   │   └── d12_2026_11_station_hour.txt.gz
│   ├── 2026-12/
│   └── 2027-01/
│
└── marts/                      # dbt 轉換產出
    ├── fct_daily_traffic.parquet
    └── dim_stations.parquet
```

#### 空間使用預估

```
Processed Parquet (100 月):  0.17 GB  (必要)
Raw Rolling (12 月):         0.60 GB  (備份)
dbt Marts:                   0.05 GB  (分析)
───────────────────────────────────────
總計:                        0.82 GB
使用率:                      8.2% (0.82 GB / 10 GB)
剩餘空間:                    9.18 GB ✅
```

#### 實作邏輯（Python 偽碼）

```python
def upload_strategy(file_type, file_date, file_path):
    """
    智慧上傳策略

    Args:
        file_type: 'raw' or 'processed'
        file_date: datetime 物件
        file_path: 本地檔案路徑
    """
    if file_type == 'processed':
        # Processed Parquet: 必定上傳
        r2_key = f"processed/{file_date.year}/{file_path.name}"
        r2_handler.upload(file_path, r2_key)
        print(f"✅ Uploaded processed: {r2_key}")

    elif file_type == 'raw':
        # Raw: 僅最近 12 個月上傳
        months_ago = (datetime.now() - file_date).days // 30

        if months_ago <= 12:
            # 最近 12 個月：上傳到 raw-rolling/
            r2_key = f"raw-rolling/{file_date.strftime('%Y-%m')}/{file_path.name}"
            r2_handler.upload(file_path, r2_key)
            print(f"🔄 Uploaded raw (rolling): {r2_key}")
        else:
            # 超過 12 個月：不上傳
            print(f"⏭️ Skipped raw upload (old): {file_path.name}")

        # 本地清理：30 天後刪除
        if months_ago > 1:  # 超過 30 天
            file_path.unlink()
            print(f"♻️ Cleaned local raw: {file_path.name}")
```

#### 環境變數控制

```bash
# .env
# R2 上傳策略
R2_UPLOAD_ENABLED=true                    # 是否啟用 R2 上傳
R2_UPLOAD_RAW=true                        # 是否上傳 Raw（滾動備份）
R2_RAW_ROLLING_MONTHS=12                  # Raw 滾動保留月數
R2_LOCAL_RAW_RETENTION_DAYS=30            # 本地 Raw 保留天數
```

---

## 🔧 Callback Hook 詳解（新手指南）

### 什麼是 Callback Hook？

**簡單定義**: Callback = 「回撥函式」= 「事件完成後，呼叫你提供的函式」

想像你在**餐廳點外帶**：

#### 沒有 Callback（傳統做法）
```
你: 我要一份炒飯
廚師: 好（開始炒飯）
你: （站在櫃台等...一直等...）
廚師: 炒飯好了！
你: （拿走炒飯離開）
```
**問題**: 你必須一直等，無法做其他事

#### 有 Callback（現代做法）
```
你: 我要一份炒飯，做好後"打電話給我"（提供 callback 函式）
廚師: 好（開始炒飯）
你: （回家做其他事...）
--- 10 分鐘後 ---
廚師: （炒飯好了！呼叫你的 callback）電話響！
你: （收到通知，去拿炒飯）
```
**優點**: 你可以做其他事，等通知再回來

---

### Python Callback 基礎範例

#### 範例 1：最簡單的 Callback

```python
# 定義一個會呼叫 callback 的函式
def cook_rice(dish_name, callback=None):
    print(f"開始煮 {dish_name}...")
    print(f"{dish_name} 煮好了！")

    # Hook: 如果提供了 callback，就呼叫它
    if callback:
        callback(dish_name)  # 執行你傳入的函式

# 定義你的 callback 函式
def notify_me(dish):
    print(f"📱 通知：{dish} 可以拿了！")

# 使用 1: 不提供 callback
cook_rice("炒飯")
# 輸出:
# 開始煮 炒飯...
# 炒飯 煮好了！

# 使用 2: 提供 callback
cook_rice("炒飯", callback=notify_me)
# 輸出:
# 開始煮 炒飯...
# 炒飯 煮好了！
# 📱 通知：炒飯 可以拿了！  ← callback 被呼叫了！
```

---

#### 範例 2：Callback 接收參數

```python
def download_file(url, filename, on_complete=None):
    """
    模擬下載檔案

    Args:
        url: 下載網址
        filename: 檔案名稱
        on_complete: 下載完成後的 callback 函式
    """
    print(f"📥 開始下載: {url}")
    # ... 下載邏輯 ...
    print(f"✅ 下載完成: {filename}")

    # 呼叫 callback，傳遞檔案資訊
    if on_complete:
        on_complete(
            filename=filename,
            size_mb=50,  # 模擬檔案大小
            success=True
        )

# 定義 callback: 上傳到雲端
def upload_to_cloud(filename, size_mb, success):
    if success:
        print(f"☁️ 上傳到雲端: {filename} ({size_mb} MB)")
    else:
        print(f"❌ 上傳失敗")

# 使用
download_file(
    url="https://example.com/data.csv",
    filename="data.csv",
    on_complete=upload_to_cloud  # 傳入 callback
)

# 輸出:
# 📥 開始下載: https://example.com/data.csv
# ✅ 下載完成: data.csv
# ☁️ 上傳到雲端: data.csv (50 MB)  ← callback 自動執行
```

---

#### 範例 3：多個 Callback（鏈式處理）

```python
def process_data(data, callbacks=[]):
    """
    處理資料，支援多個 callback

    Args:
        data: 要處理的資料
        callbacks: callback 函式列表
    """
    print(f"處理資料: {data}")
    result = data.upper()  # 模擬處理

    # 依序呼叫所有 callback
    for callback in callbacks:
        callback(result)

    return result

# 定義多個 callback
def save_to_file(data):
    print(f"💾 儲存到檔案: {data}")

def upload_to_r2(data):
    print(f"☁️ 上傳到 R2: {data}")

def send_notification(data):
    print(f"📧 發送通知: 資料處理完成")

# 使用: 一次註冊多個 callback
process_data(
    data="hello world",
    callbacks=[
        save_to_file,
        upload_to_r2,
        send_notification
    ]
)

# 輸出:
# 處理資料: hello world
# 💾 儲存到檔案: HELLO WORLD
# ☁️ 上傳到 R2: HELLO WORLD
# 📧 發送通知: 資料處理完成
```

---

### 在 PeMS 專案中的應用

#### 現況（沒有 Callback）

```python
# scripts/monthly_download.py (目前版本)
pems = PeMSHandler(username, password)
pems.download_files(...)

# 下載完成後...什麼都不做
# 如果要上傳 R2，得自己手動處理
```

#### 改進後（有 Callback Hook）

```python
# src/pems/core/handler.py (新增 Hook)
class PeMSHandler:
    def download_files(self, ..., post_download_callback=None):
        """
        下載檔案，支援 callback

        Args:
            post_download_callback: 下載完成後要執行的函式
        """
        for file in files_to_download:
            success = self._download_file(file)

            if success and post_download_callback:
                # Hook: 呼叫你提供的處理函式
                post_download_callback(
                    file_path=Path(save_path) / file["file_name"],
                    file_metadata=file
                )
```

**使用範例 1：只下載，不處理**

```python
# 不提供 callback
pems.download_files(
    start_year=2024,
    end_year=2024,
    districts=["12"],
    file_types=["station_hour"],
    months=["January"],
    save_path="data/raw/"
)
# 結果：只下載，不做任何後續處理
```

**使用範例 2：下載完自動上傳 R2**

```python
from src.pems.storage import R2StorageHandler

r2_handler = R2StorageHandler()

def upload_after_download(file_path, file_metadata):
    """下載完成後的處理邏輯"""
    print(f"處理檔案: {file_path}")

    # 1. 處理成 Parquet
    parquet_path = process_to_parquet(file_path)

    # 2. 上傳到 R2
    r2_key = f"processed/{file_metadata['year']}/{parquet_path.name}"
    r2_handler.upload_file(parquet_path, r2_key)
    print(f"✅ 上傳完成: {r2_key}")

    # 3. 清理本地 raw（30 天後）
    cleanup_old_files(file_path, days=30)

# 使用 Hook
pems.download_files(
    ...,
    post_download_callback=upload_after_download  # ✨ 傳入 callback
)

# 結果：
# 1. 下載 d12_2024_01.txt.gz
# 2. 自動呼叫 upload_after_download()
#    - 處理成 Parquet
#    - 上傳到 R2
#    - 清理舊檔案
# 3. 繼續下載下一個檔案...
```

**使用範例 3：靈活組合（Data Science 工作流程）**

```python
def my_data_pipeline(file_path, file_metadata):
    """客製化資料 pipeline"""
    # Step 1: 資料驗證
    if not validate_file(file_path):
        print(f"❌ 驗證失敗: {file_path}")
        return

    # Step 2: 處理
    df = pd.read_csv(file_path)
    df_clean = clean_data(df)

    # Step 3: 特徵工程
    df_features = extract_features(df_clean)

    # Step 4: 儲存多種格式
    df_features.to_parquet("data/processed/features.parquet")
    df_features.to_csv("data/processed/features.csv")

    # Step 5: 上傳到 R2
    upload_to_r2("data/processed/features.parquet")

    # Step 6: 訓練模型（如果需要）
    if file_metadata['month'] == 'December':  # 年底重新訓練
        train_model(df_features)

    print(f"✅ Pipeline 完成: {file_path.name}")

# 使用你的客製化 pipeline
pems.download_files(
    ...,
    post_download_callback=my_data_pipeline
)
```

---

### Callback Hook 的優勢

| 特性 | 沒有 Hook | 有 Hook |
|------|----------|---------|
| **彈性** | 修改核心邏輯才能加功能 | 傳入不同 callback 即可 |
| **可測試性** | 難測試（功能耦合） | 容易測試（獨立測試 callback） |
| **可維護性** | 核心程式碼越來越複雜 | 核心邏輯保持簡潔 |
| **可重用性** | 難重用（綁死流程） | 高度可重用（任意組合） |
| **開發速度** | 每次改功能要改核心 | 快速迭代（只寫 callback） |

---

### 常見的 Callback 模式

#### 模式 1：單一 Callback

```python
def process(data, callback=None):
    result = do_something(data)
    if callback:
        callback(result)
```

#### 模式 2：多個 Callbacks（事件觸發）

```python
def process(data, on_start=None, on_progress=None, on_complete=None):
    if on_start:
        on_start()

    for i, item in enumerate(data):
        # 處理...
        if on_progress:
            on_progress(progress=i/len(data))

    if on_complete:
        on_complete(result)
```

#### 模式 3：Callback 返回值影響流程

```python
def process(data, validator=None):
    for item in data:
        # 如果提供了驗證 callback，先驗證
        if validator:
            is_valid = validator(item)
            if not is_valid:
                continue  # 跳過無效資料

        # 處理有效資料
        process_item(item)
```

---

### 延伸學習：Callback 在其他地方的應用

你會在很多地方看到 Callback 模式：

#### JavaScript
```javascript
// 點擊事件的 callback
button.addEventListener('click', function() {
    alert('按鈕被點擊了！');
});

// API 請求的 callback
fetch('/api/data')
    .then(response => response.json())  // callback
    .then(data => console.log(data));   // callback
```

#### Python Flask
```python
@app.route('/api/users')
def get_users():  # 這是一個 callback（路由處理器）
    return jsonify(users)
```

#### React
```python
function Button() {
    const handleClick = () => {  // callback 函式
        alert('Clicked!');
    };

    return <button onClick={handleClick}>Click me</button>;
}
```

#### Apache Airflow
```python
# Airflow 的 python_callable 就是 callback
task = PythonOperator(
    task_id='process_data',
    python_callable=my_processing_function  # callback
)
```

---

### 總結：為什麼要用 Callback Hook？

1. ✅ **不修改核心邏輯**：下載器保持簡潔，只負責下載
2. ✅ **靈活擴展**：傳入不同 callback 做不同事情
3. ✅ **易於測試**：callback 可以獨立測試
4. ✅ **符合開放封閉原則**：對擴展開放，對修改封閉
5. ✅ **業界標準模式**：JavaScript、React、Airflow 都這樣做

**記住**: Callback = 「事件發生後，執行你提供的函式」

---

## 📦 Phase 1: R2 上傳功能

### 目標
整合 R2 上傳功能到下載流程，實作智慧儲存策略

### 參考資源
- `cloud-test/3_r2_test/upload_to_r2.py`
- `cloud-test/notes/step2-cloudflare-r2.md`

### 實作計畫

#### 1.1 新增 R2 儲存處理器
**檔案**: `src/pems/storage.py` (新建)

**功能**:
```python
class R2StorageHandler:
    - upload_file(local_path, r2_key)
    - upload_directory(local_dir, r2_prefix)
    - list_files(prefix)
    - download_file(r2_key, local_path)
```

#### 1.2 更新配置
**檔案**: `config/settings.py`

**新增**:
```python
# R2 Configuration
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "pems-processed")
R2_UPLOAD_ENABLED = os.getenv("R2_UPLOAD_ENABLED", "false").lower() == "true"
```

#### 1.3 整合到下載流程
**檔案**: `src/pems/core/handler.py`

**修改點**:
- 下載完成後呼叫 R2 上傳
- 可選：上傳成功後刪除本地檔案（節省空間）
- 錯誤處理與重試機制

#### 1.4 更新相依套件
**檔案**: `pyproject.toml`

**新增**:
```toml
dependencies = [
    ...
    "boto3>=1.34.10",
]
```

### 測試計畫
- [ ] 單元測試: R2StorageHandler 各方法
- [ ] 整合測試: 下載 → 處理 → 上傳 R2 完整流程
- [ ] 錯誤情境: 網路斷線、憑證錯誤、Bucket 不存在

### 驗收標準
- ✅ 下載完成後自動上傳到 R2
- ✅ 上傳進度追蹤與日誌記錄
- ✅ 錯誤處理與重試機制
- ✅ 環境變數控制是否啟用 R2 上傳

---

## 🗄️ Phase 2: DuckDB 整合

### 目標
支援本地與 R2 Parquet 檔案的高效查詢

### 參考資源
- `cloud-test/2_duckdb_test/query_local.py`
- `cloud-test/2_duckdb_test/query_r2.py`

### 實作計畫

#### 2.1 新增 DuckDB 查詢引擎
**檔案**: `src/pems/query.py` (新建)

**功能**:
```python
class DuckDBQueryEngine:
    - __init__(db_path=":memory:", r2_config=None)
    - query_local(parquet_path, sql=None)
    - query_r2(s3_uri, sql=None)
    - create_view(name, source)
    - execute(sql)
```

#### 2.2 更新 Dashboard 使用 DuckDB
**檔案**: `scripts/dashboard.py`

**修改**:
- 取代 `pd.read_parquet()` 為 DuckDB 查詢
- 支援本地與 R2 資料源切換
- Cache DuckDB 連線

#### 2.3 新增查詢腳本
**檔案**: `scripts/query_data.py` (新建)

**功能**:
- CLI 工具查詢本地/R2 資料
- 匯出查詢結果

### 測試計畫
- [ ] 本地 Parquet 查詢效能
- [ ] R2 Parquet 查詢（需 R2 憑證）
- [ ] 複雜 SQL 查詢（JOIN, GROUP BY, 時間範圍）
- [ ] Dashboard 整合測試

### 驗收標準
- ✅ Dashboard 可切換本地/R2 資料源
- ✅ 查詢效能優於直接 pd.read_parquet()
- ✅ 支援複雜 SQL 聚合查詢
- ✅ 提供 CLI 查詢工具

---

## 🔄 Phase 3: dbt 資料轉換

### 目標
建立結構化的資料轉換層（Staging → Intermediate → Marts）

### 參考資源
- `cloud-test/2_duckdb_test/dbt_mini/`
- `cloud-test/notes/step4-dbt-setup.md`

### 實作計畫

#### 3.1 設定 dbt 專案
**位置**: `dbt_pems/` (專案根目錄)

**結構**:
```
dbt_pems/
├── dbt_project.yml
├── profiles.yml
└── models/
    ├── staging/
    │   ├── stg_traffic_raw.sql
    │   └── sources.yml
    ├── intermediate/
    │   └── int_hourly_stats.sql
    └── marts/
        └── fct_daily_traffic.sql
```

#### 3.2 定義資料模型

**Staging Layer** (清理):
- `stg_traffic_raw`: 移除異常值、時間處理、型別轉換

**Intermediate Layer** (聚合):
- `int_hourly_stats`: 每小時統計（流量、速度、佔有率）

**Marts Layer** (業務產出):
- `fct_daily_traffic`: 每日交通指標（給 Dashboard 使用）

#### 3.3 配置 profiles.yml
**連接**: DuckDB (本地或 R2)

```yaml
pems:
  outputs:
    dev:
      type: duckdb
      path: 'data/duckdb/pems_analytics.db'
    prod:
      type: duckdb
      path: 's3://pems-processed/analytics/pems.db'
```

#### 3.4 新增執行腳本
**檔案**: `scripts/run_dbt.py`

**功能**:
```bash
# 執行所有 models
uv run python scripts/run_dbt.py run

# 執行測試
uv run python scripts/run_dbt.py test

# 生成文件
uv run python scripts/run_dbt.py docs
```

### 測試計畫
- [ ] dbt run 無錯誤
- [ ] dbt test 全部通過
- [ ] 資料品質檢查（not_null, unique, accepted_range）
- [ ] 轉換邏輯驗證（對比原始資料）

### 驗收標準
- ✅ 完整的三層資料模型（Staging/Intermediate/Marts）
- ✅ 資料測試覆蓋率 > 80%
- ✅ 自動生成文件
- ✅ Dashboard 可使用 dbt 產出的 marts

---

## 🔀 Phase 4: Airflow 工作流程編排

### 目標
自動化整個 ETL pipeline

### 參考資源
- `cloud-test/4_airflow_local/`
- `cloud-test/notes/step3-airflow-render.md`

### 實作計畫

#### 4.1 設定 Airflow 環境
**位置**: `airflow/` (專案根目錄)

**結構**:
```
airflow/
├── docker-compose.yml
├── dags/
│   └── pems_etl_dag.py
├── logs/
└── plugins/
```

#### 4.2 定義 ETL DAG

**DAG 名稱**: `pems_daily_etl`

**Tasks**:
```python
download_task       # 下載原始資料
    ↓
process_task        # 清理與處理
    ↓
upload_r2_task      # 上傳到 R2
    ↓
dbt_run_task        # 執行 dbt 轉換
    ↓
dbt_test_task       # 執行資料測試
    ↓
cleanup_task        # 清理本地檔案
```

**排程**: 每日凌晨 2:00 執行

#### 4.3 任務實作

**Download Task**:
```python
PythonOperator(
    task_id='download_pems_data',
    python_callable=download_pems_data,
    provide_context=True,
)
```

**dbt Task**:
```python
BashOperator(
    task_id='dbt_run',
    bash_command='cd /opt/airflow/dbt_pems && dbt run',
)
```

#### 4.4 本地測試環境
```bash
# 啟動 Airflow
cd airflow
docker-compose up -d

# 訪問 UI
open http://localhost:8080
```

### 測試計畫
- [ ] 本地 Docker Airflow 運行
- [ ] DAG 手動觸發測試
- [ ] 完整 pipeline 端到端測試
- [ ] 錯誤處理與重試機制

### 驗收標準
- ✅ DAG 定義無語法錯誤
- ✅ 所有 tasks 成功執行
- ✅ 錯誤自動重試（最多 3 次）
- ✅ 執行日誌完整可追蹤
- ✅ 提供本地測試環境（Docker Compose）

---

## 🧪 Phase 5: 整合測試與部署

### 目標
完整流程測試並準備生產部署

### 測試清單

#### 5.1 本地完整流程測試
- [ ] 下載 → 處理 → R2 上傳
- [ ] DuckDB 查詢本地與 R2 資料
- [ ] dbt 轉換執行成功
- [ ] Airflow DAG 完整執行
- [ ] Dashboard 顯示最新資料

#### 5.2 效能測試
- [ ] 單月資料處理時間 < 10 分鐘
- [ ] R2 上傳速度（測量網路頻寬）
- [ ] DuckDB 查詢回應時間 < 2 秒
- [ ] Dashboard 載入時間 < 5 秒

#### 5.3 錯誤復原測試
- [ ] 下載中斷 → 斷點續傳
- [ ] R2 上傳失敗 → 重試機制
- [ ] dbt 測試失敗 → 停止 pipeline
- [ ] Airflow task 失敗 → 告警與重試

### 部署準備

#### 文件更新
- [ ] `README.md`: 加入新功能說明
- [ ] `docs/SETUP.md`: 環境設定指南
- [ ] `docs/AIRFLOW_DEPLOYMENT.md`: Airflow 部署說明
- [ ] `docs/DBT_GUIDE.md`: dbt 使用手冊

#### 環境變數範本
**檔案**: `.env.example`

```bash
# PeMS Credentials
PEMS_USERNAME=your_username
PEMS_PASSWORD=your_password

# R2 Configuration
R2_ENDPOINT=https://account_id.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET=pems-processed
R2_UPLOAD_ENABLED=true

# DuckDB
DUCKDB_PATH=data/duckdb/pems.db

# Airflow (for production)
AIRFLOW__CORE__EXECUTOR=LocalExecutor
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://...
```

### 驗收標準
- ✅ 完整端到端測試通過
- ✅ 所有文件更新完成
- ✅ `.env.example` 提供完整配置範本
- ✅ 本地與雲端環境都可運行
- ✅ 提供故障排除指南

---

## 📊 專案結構（最終版）

```
caltrans-pems-etl/
├── src/pems/
│   ├── core/
│   │   └── handler.py          # 下載邏輯 + R2 上傳整合
│   ├── storage.py              # ✨ 新增: R2StorageHandler
│   └── query.py                # ✨ 新增: DuckDBQueryEngine
│
├── scripts/
│   ├── dashboard.py            # 🔄 更新: 使用 DuckDB 連線
│   ├── data_processor.py       # 保持現有
│   ├── monthly_download.py     # 保持現有
│   ├── run_dbt.py              # ✨ 新增: dbt 執行腳本
│   └── query_data.py           # ✨ 新增: CLI 查詢工具
│
├── dbt_pems/                   # ✨ 新增: dbt 專案
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/
│       ├── staging/
│       ├── intermediate/
│       └── marts/
│
├── airflow/                    # ✨ 新增: Airflow 配置
│   ├── docker-compose.yml
│   ├── dags/
│   │   └── pems_etl_dag.py
│   └── logs/
│
├── config/
│   └── settings.py             # 🔄 更新: 加入 R2、DuckDB 配置
│
├── cloud-test/                 # 保留: 學習文件與原型
│   ├── notes/
│   │   ├── step1-local-etl.md
│   │   ├── step2-cloudflare-r2.md
│   │   ├── step3-airflow-render.md
│   │   ├── step4-dbt-setup.md
│   │   └── step5-streamlit-render.md
│   └── [1-5]_*/                # 原型實作（參考用）
│
├── docs/                       # ✨ 新增: 完整文件
│   ├── SETUP.md
│   ├── AIRFLOW_DEPLOYMENT.md
│   ├── DBT_GUIDE.md
│   └── TROUBLESHOOTING.md
│
├── notebook/
│   └── etl-modernization.md    # ✨ 本文件
│
└── .env.example                # ✨ 新增: 環境變數範本
```

---

## 🎓 學習成果與技能提升

完成此專案後，你將掌握：

### 技術能力
- ✅ **雲端儲存**: Cloudflare R2 (S3-compatible API)
- ✅ **現代資料倉儲**: DuckDB (OLAP 分析)
- ✅ **資料轉換**: dbt (ELT 架構)
- ✅ **工作流程編排**: Apache Airflow (DAG 開發)
- ✅ **容器化**: Docker & Docker Compose
- ✅ **資料視覺化**: Streamlit Dashboard

### 架構設計
- ✅ ELT vs ETL 架構決策
- ✅ 資料分層 (Staging/Intermediate/Marts)
- ✅ 雲端與本地混合架構
- ✅ 可擴展的 pipeline 設計

### 工程最佳實踐
- ✅ 模組化程式碼設計
- ✅ 錯誤處理與重試機制
- ✅ 日誌記錄與監控
- ✅ 環境變數管理
- ✅ 文件與測試

---

## 📅 時程規劃

### 建議執行順序

**Week 1-2**: Phase 0-1 (基礎整合)
- Phase 0: 程式碼審查 (1 天)
- Phase 1: R2 上傳功能 (2-3 天)
- 測試與除錯 (1 天)

**Week 3**: Phase 2 (查詢層)
- DuckDB 整合 (2-3 天)
- Dashboard 更新 (1 天)
- 測試 (1 天)

**Week 4**: Phase 3 (轉換層)
- dbt 模型開發 (2-3 天)
- 測試與文件 (1 天)

**Week 5**: Phase 4 (編排層)
- Airflow DAG 開發 (2-3 天)
- 本地測試 (1 天)

**Week 6**: Phase 5 (整合與部署)
- 端到端測試 (2 天)
- 文件更新 (1 天)
- 部署準備 (1-2 天)

**總時程**: 4-6 週（兼職進行）

---

## 🔗 參考資源

### 官方文件
- [Cloudflare R2 Docs](https://developers.cloudflare.com/r2/)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [dbt Documentation](https://docs.getdbt.com/)
- [Apache Airflow Docs](https://airflow.apache.org/docs/)

### 專案內部
- `cloud-test/notes/`: 各步驟詳細說明
- `cloud-test/[1-5]_*/`: 原型實作參考

### 外部學習
- [Modern Data Stack](https://www.getdbt.com/analytics-engineering/modular-data-modeling-technique/)
- [ELT vs ETL](https://www.fivetran.com/blog/elt-vs-etl)
- [Airflow Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)

---

## ✅ 里程碑檢查點

### Phase 完成標準

**Phase 1 完成**:
- [ ] R2StorageHandler 類別實作完成
- [ ] 下載流程整合 R2 上傳
- [ ] 環境變數配置完成
- [ ] 單元測試通過
- [ ] 至少一次完整的下載→上傳成功

**Phase 2 完成**:
- [ ] DuckDBQueryEngine 實作完成
- [ ] Dashboard 使用 DuckDB 查詢
- [ ] 本地與 R2 資料源皆可查詢
- [ ] 查詢效能測試通過

**Phase 3 完成**:
- [ ] dbt 專案結構建立
- [ ] 三層 models 實作完成
- [ ] dbt run/test 全部通過
- [ ] 自動生成文件

**Phase 4 完成**:
- [ ] Airflow DAG 定義完成
- [ ] 本地 Docker 環境運行
- [ ] 完整 pipeline 執行成功
- [ ] 錯誤處理測試通過

**Phase 5 完成**:
- [ ] 端到端測試通過
- [ ] 所有文件更新
- [ ] 部署指南完成
- [ ] 合併到 main 分支

---

## 🚀 開始行動

**目前狀態**: Phase 0 - 程式碼審查

**下一步**:
1. 審查 `src/pems/core/handler.py` 下載邏輯
2. 識別 R2 上傳整合點
3. 列出改進建議清單

**準備好了嗎？** Let's modernize this ETL! 🎉

---

**最後更新**: 2025-10-12
**維護者**: Yu-Jen Chen
**分支**: feature/etl-modernization
