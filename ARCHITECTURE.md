# 立 AI Agent 系統架構文檔

## 📐 系統架構圖

```
┌─────────────────────────────────────────────────────────────┐
│                    立 AI Agent 系統                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐    ┌──────────────┐  ┌─────────────┐  │
│  │  desktop_agent  │    │ ai_bridge    │  │   workshop  │  │
│  │   (PyQt6 GUI)   │    │ (Telegram)   │  │    UI       │  │
│  └────────┬────────┘    └──────┬───────┘  └─────────────┘  │
│           │                    │                            │
│           └────────────────────┼────────────────────────────┤
│                                │                            │
│              ┌─────────────────▼─────────────────┐          │
│              │   Lobster_Core  (核心引擎)        │          │
│              │  ✓ Lazy Loading                   │          │
│              │  ✓ 統一接口                       │          │
│              └─────────────────┬─────────────────┘          │
│                                │                            │
│  ┌────────────────────────────▼───────────────────────┐    │
│  │            功能子系統                              │    │
│  │                                                    │    │
│  │  repair_engine        ← 自動修復                 │    │
│  │  error_detector       ← 錯誤偵測                 │    │
│  │  task_scheduler       ← 任務調度                 │    │
│  │  autonomous_dev       ← 自主開發                 │    │
│  │  knowledge_store      ← 知識庫                   │    │
│  │  memory_engine        ← 記憶系統                 │    │
│  │  prompt_engine        ← 提示詞引擎               │    │
│  │  ...                                              │    │
│  └────────────────────────┬───────────────────────────┘    │
│                           │                                 │
│  ┌────────────────────────▼───────────────────────────┐    │
│  │              基礎設施層                            │    │
│  │                                                    │    │
│  │  agent_logger         ← 統一日誌                  │    │
│  │  config_manager       ← 配置管理                  │    │
│  │  ollama_guard         ← Ollama 守衛               │    │
│  │  memory_systems       ← 記憶體系                  │    │
│  │  ...                                              │    │
│  └────────────────────────┬───────────────────────────┘    │
│                           │                                 │
│              ┌────────────▼──────────────┐                 │
│              │   Ollama + LLM 模型      │                 │
│              │  (本地推論)               │                 │
│              └───────────────────────────┘                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔗 模組依賴關係

### 第一層：UI/入口層
```
desktop_agent.py  ──┐
                     ├──→ Lobster_Core (核心)
ai_bridge.py  ─────┘
workshop_ui.py ────┘
```

### 第二層：核心系統
```
Lobster_Core
    ├─→ repair_engine        (修復)
    ├─→ error_detector       (偵測)
    ├─→ task_scheduler       (調度)
    ├─→ prompt_engine        (提示詞)
    ├─→ episodic_memory      (情景記憶)
    ├─→ reflex_memory        (反射記憶)
    └─→ reasoning_supervisor (推理監督)
```

### 第三層：功能模組
```
autonomous_dev.py
    ├─→ ollama_guard
    ├─→ pc_api_client
    └─→ screenshot_copy_strategy

repair_engine.py
    ├─→ syntax_classifier
    ├─→ syntax_rewriter
    └─→ repair_validator

knowledge_store.py
    ├─→ long_term_memory
    └─→ memory_curator
```

### 第四層：基礎設施
```
agent_logger.py
config_manager.py
ollama_guard.py
```

---

## 📦 主要模組說明

### 核心模組

#### `Lobster_Core.py` - 核心引擎
- **職責**：統一接口、Lazy Loading
- **特點**：只在使用時才初始化子系統
- **依賴**：所有功能模組（延遲加載）

#### `repair_engine.py` - 修復引擎
- **職責**：自動檢測和修復代碼錯誤
- **流程**：
  1. 語法檢測
  2. 啟發式修復（快速）
  3. LLM 修復（精確）
  4. 驗證修復結果
- **備份**：自動保存 `.repair_backup/`

#### `error_detector.py` - 錯誤偵測
- **職責**：多層次錯誤檢測
- **檢測類型**：
  1. 語法錯誤（AST）
  2. Runtime 錯誤（執行）
  3. 頂層執行檢測

#### `task_scheduler.py` - 任務調度
- **職責**：多步驟任務編排和執行
- **特點**：
  - 支持重試機制
  - 步驟間共享狀態
  - 故障自動恢復
- **內置任務**：
  - `create_auto_repair_task()`
  - `create_code_review_task()`

### AI 橋接模組

#### `ai_bridge.py` - Telegram 橋接
- **職責**：Telegram 消息轉發
- **特點**：
  - 環境變數配置
  - 本地 Ollama 推論
  - 線程安全

#### `autonomous_dev.py` - 自主開發
- **職責**：從需求到代碼生成
- **流程**：
  1. 規劃架構
  2. 逐個生成文件
  3. 語法檢查
  4. 執行測試
  5. 生成文檔

#### `desktop_agent.py` - 桌面控制台
- **職責**：完整 UI 界面
- **功能**：
  - 對話交互
  - 語音輸入
  - 器官庫管理
  - 工坊集成

### 記憶系統

#### `long_term_memory.py` - 長期記憶
- 持久化存儲（JSON/數據庫）
- 用于跨會話記憶

#### `episodic_memory.py` - 情景記憶
- 事件序列記憶
- 上下文恢復

#### `reflex_memory.py` - 反射記憶
- 快速應答庫
- 實時更新

---

## 🔄 常用業務流程

### 自動修復流程

```
輸入 (錯誤信息)
    ↓
[1] 錯誤偵測 (error_detector)
    ↓
[2] 備份原始碼
    ↓
[3] 啟發式修復 (快速嘗試)
    ↓
    ✓ 成功? → 驗證 → 完成
    ✗ 失敗? ↓
[4] LLM 修復 (精確修復)
    ↓
    ✓ 成功? → 驗證 → 完成
    ✗ 失敗? ↓
[5] 還原原始碼 + 記錄失敗
    ↓
輸出 (修復結果或失敗原因)
```

### 自主開發流程

```
需求 (用戶輸入)
    ↓
[1] 架構規劃 (LLM)
    ↓
[2] 遍歷每個文件
    ├─ [2.1] 收集上下文
    ├─ [2.2] 代碼生成 (LLM)
    ├─ [2.3] 語法檢查 (AST)
    ├─ [2.4] 修復語法錯誤 (如需)
    └─ [2.5] 寫入文件
    ↓
[3] 測試驗證
    ↓
[4] 生成文檔 (README.md)
    ↓
[5] 通知完成
    ↓
輸出 (完整項目)
```

### 任務調度流程

```
任務提交
    ↓
加入隊列（按優先級排序）
    ↓
取出任務 → 執行步驟
    ├─ 步驟 1
    ├─ 步驟 2 (可讀取步驟 1 結果)
    ├─ 步驟 3
    └─ ...
    ↓
任務完成或失敗
    ↓
記錄歷史
```

---

## 🔧 配置系統

### 配置層級

1. **默認值** (硬編碼)
2. **環境變數** (`.env`)
3. **配置文件** (`config.json`)
4. **運行時設置** (代碼中修改)

### 配置訪問

```python
from config_manager import get_config

config = get_config()

# 取得值
token = config.get("TELEGRAM_TOKEN")
model = config.get("DEFAULT_MODEL", "gemma4")

# 設置值
config.set("DEBUG_MODE", True)

# 驗證配置
valid, errors = config.validate()

# 顯示摘要
config.print_summary()
```

---

## 🎯 設計原則

### 1. 分層設計
- UI 層與邏輯層分離
- 易于替換和測試
- 清晰的責任邊界

### 2. Lazy Loading
- 按需初始化
- 減少啟動時間
- 節省內存

### 3. 配置外部化
- 敏感信息不入代碼
- 環境變數優先
- 易于部署

### 4. 錯誤恢復
- 自動備份
- 失敗還原
- 重試機制

### 5. 透明性
- 詳細日誌
- 進度回調
- 結果記錄

---

## 🧪 測試架構

### 單元測試

```python
# tests/test_repair_engine.py
def test_fix_zero_division():
    engine = RepairEngine()
    # ...
```

### 集成測試

```python
# tests/test_task_scheduler.py
def test_auto_repair_task():
    scheduler = TaskScheduler()
    # ...
```

### 運行測試

```bash
pytest -v                           # 運行所有測試
pytest tests/ --cov=.             # 生成覆蓋率
pytest -k "repair" -v             # 運行特定測試
```

---

## 📊 性能考慮

### 優化點

1. **Lazy Loading**：減少初始化時間
2. **異步調度**：不阻塞 UI
3. **增量修復**：只修改出錯行
4. **重試機制**：失敗自動嘗試

### 監控

```python
import logging
logger = logging.getLogger("performance")
logger.info(f"修復耗時：{elapsed}ms")
```

---

## 🔐 安全架構

### 敏感信息
- Telegram Token → `.env` (環境變數)
- 群組 ID → `.env`
- 模型地址 → `.env`

### 代碼執行
- 修復引擎備份原始碼
- 修復失敗自動還原
- 隔離執行環境 (subprocess)

### 訪問控制
- 群組 ID 驗證（Telegram）
- 白名單機制
- 日誌審計

---

## 📈 擴展方式

### 添加新模組

1. 在對應目錄創建新文件
2. 實現標準接口
3. 在 `Lobster_Core` 中註冊（Lazy Loading）
4. 添加單元測試

### 添加新功能

1. 在 `task_scheduler` 中添加步驟處理
2. 實現對應模組
3. 在 `ModuleRunner._try_dynamic()` 中註冊
4. 測試和文檔

---

## 📚 相關文檔

- 🔧 [設置指南](SETUP_GUIDE.md)
- 🐛 [故障排查](SETUP_GUIDE.md#-故障排查)
- 📖 [API 文檔](API.md)（待補充）
