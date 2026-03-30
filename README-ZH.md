# HLS Knowledge Base — 系統管理與使用指南

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![For Education](https://img.shields.io/badge/Use-Education%20%26%20Academic-green.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

> Copyright (c) 2026 AICOFORGE. Licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
> Educational and academic use is freely permitted with attribution. AMD/Xilinx authorized partners may use this for course integration.
> For commercial licensing: kevinjan@aicoforge.com
> 
> This Architecture, domain knowledge, and design decisions are original work by AICOFORGE.

---

[English](./README.md) | 中文

---

> **項目名稱**: cursor-hls-kb  
> **版本**: v1.0
> 
> **目標讀者**: 知識庫管理員 / Cursor HLS 使用者

---

## 特色

- **集中式知識庫**：以資料庫統一儲存 HLS 官方規則（UG1399）與實際優化經驗，並追蹤各規則的應用成效
- **Cursor AI 自動化**：使用者透過 Cursor Remote SSH 在 Vitis-HLS 機器上進行設計，Cursor 在設計過程中會查詢最佳優化案例，使每次決策皆有知識庫依據，合成後將迭代資訊、效能結果、套用規則等寫入知識庫
- **精準回滾機制**：利用 `_rollback_info` 元數據，可針對特定迭代或整個專案精確還原資料庫狀態，支援回滾預覽
- **輕量 API 存取**：API 服務（port 8000）提供規則查詢、迭代記錄、合成結果等端點，Cursor 操作 Vitis-HLS 機器透過內網直接呼叫，無需額外部署
- **可視化資料檢視**：管理者與使用者皆可透過 DBeaver 直接查看資料庫，方便管理及檢視 Cursor 自動化寫入的資料

---

## 概述

儲存庫提供 HLS（高層次合成）知識庫系統的基礎設施和工具，包括資料庫管理、備份恢復、回滾機制，以及與 Cursor AI 協作的設計工作流程。

---

## 系統架構

<p align="center">
  <img src="https://github.com/user-attachments/assets/a935fdda-f26c-41cb-a25e-06a191928c2f" width="70%">
</p>

**存取方式**：

- **Cursor AI Agent** — 透過 **SSH** 連線至 Vitis-HLS 主機，再經由內網存取 HLS 知識庫主機的 **FastAPI** 服務（port 8000）進行資料讀寫
- **DBeaver** — 透過 **SSH Tunnel / 直連** 方式連線至 Vitis-HLS 主機，再經由內網存取 HLS 知識庫主機的 **PostgreSQL**（port 5432）。管理員具備讀寫權限，使用者僅限讀取

---

## 資料庫架構

### 實體表（5 張）

| 表名                    | 用途                           |
| --------------------- | ---------------------------- |
| `hls_rules`           | 規則定義（R### 官方規則 / P### 用戶自定義） |
| `projects`            | 專案基本資訊                       |
| `design_iterations`   | 每次設計迭代的相關資訊                  |
| `synthesis_results`   | HLS 合成結果（II、延遲、資源）           |
| `rules_effectiveness` | 規則應用效果追蹤統計                   |

### 視圖（2 個）

| 視圖名                          | 用途                                                   |
| ---------------------------- | ---------------------------------------------------- |
| `rule_effectiveness_summary` | 規則成功率彙總（動態計算）                                        |
| `best_designs_by_type`       | 每個 project_type 中 ii_achieved 最小的設計記錄，供快速查詢各類型最佳設計基準 |

---

## 機器配置

範例環境包含 3 台位於相同內網的機器，透過外網 IP `hls-external-ip` 使用不同 port forwarding 可各別連接到這 3 台機器。系統管理員需要先完成 HLS01 知識庫主機的安裝與初始化（含 PostgreSQL、FastAPI 部署及規則匯入），使用者的 Vitis-HLS 主機運作 Cursor 自動化 HLS 設計時才可以由知識庫取得資料。

| 機器        | 角色          | 內網 IP（範例）    | 外網 Port Forwarding（範例） | 說明                            |
| --------- | ----------- | ------------ | ---------------------- | ----------------------------- |
| **HLS01** | 知識庫主機       | 192.168.1.11 | hls-external-ip:1100   | 管理員安裝設置， PostgreSQL + FastAPI |
| **HLS02** | Vitis-HLS主機 | 192.168.1.12 | hls-external-ip:1200   | 使用者透過Cursor 代理 Vitis-HLS 設計   |
| **HLS03** | Vitis-HLS主機 | 192.168.1.13 | hls-external-ip:1300   | 使用者透過Cursor 代理 Vitis-HLS 設計   |

> 實際連線配置可依環境不同而調整，上述網路配置僅供參考。

---

## 管理員快速開始

### 前置條件

- **作業系統**：Ubuntu 22.04+（建議）
- **Docker**、**Docker Compose**、**Python 3**、**pip3**、**curl**、**asyncpg**、**pyyaml**

以上套件由 `env_setup.sh` 自動檢測並安裝，執行後摘要如下：

```
==============================
 環境檢測完成
==============================
curl             7.81.0
python3          3.10.12
docker           29.3.0
docker-compose   v5.1.0

[✓] 安裝完成！請執行以下指令套用 docker 群組（只需一次）：

    newgrp docker
```

執行方式：

```bash
chmod +x ./env_setup.sh
sudo ./env_setup.sh
newgrp docker
```

### 管理員目錄

**位置**: `~/hls-kb/`

```
hls-kb/
├── kbapi.py                 # FastAPI 服務
├── init.sql.in              # 資料庫 schema 來源
├── init.sql                 # 由 setup.sh 產生（執行後自動建立）
├── docker-compose.yml       # 容器編排（PostgreSQL + API）
├── Dockerfile               # API 容器映像
├── requirements.txt         # Python 依賴套件
├── setup.sh                 # 安裝腳本
├── import_rules.py          # 匯入規則（官方規則 + 用戶自定義）
├── rules_ug1399.txt         # 官方規則來源
├── rules_user_defined.txt   # 用戶自定義來源
└── util/
    ├── backup_restore.py    # 備份與恢復工具
    ├── logger-rollback.py   # 回滾工具
    └── reset_database.py    # 清空資料庫工具（不重建 schema）
```

### 初始化系統

```bash
cd ~/hls-kb/
chmod +x ./setup.sh
./setup.sh
```

`setup.sh` 頂部定義了環境變數（資料庫帳號、密碼、port 等），**首次使用前請改為自己的帳號密碼**；其餘參數（port、DB 名稱等）如無特殊需求可沿用預設值。

```bash
# ==================== 環境變數定義（直接修改此區塊） ====================
KB_API_PORT=8000
DB_HOST=localhost
DB_ADMIN=admin              # 管理員帳號（知識庫主機使用，讀寫權限）
DB_ADMIN_PASS=admin_passwd
DB_USER=hls_user            # 一般帳號（Vitis-HLS 主機使用，唯讀權限）
DB_PASS=hls_user_passwd
DB_NAME=hls_knowledge
DB_PORT=5432
# ======================================================================
```

> **注意：`DB_USER` 不可設為 `user`**，`user` 為 PostgreSQL 保留關鍵字（SQL standard reserved word），直接用於 `CREATE USER user ...` 會導致語法錯誤，使該帳號建立失敗。

 完成 `setup.sh` 後輸出如下：

```
===========================================================
最終驗證
============================================================

資料庫統計：
  官方規則   (official):     287
  用戶自定義 (user_defined): 104
  ─────────────────────────────
  總計:                     391

API 測試：
  規則查詢: ✓

============================================================
✓ 初始化完成！
============================================================

下一步：
  訪問 API: curl http://localhost:8000/health
```

`setup.sh` 執行的主要步驟：

- 從 `init.sql.in` 透過 `sed` 產生 `init.sql`
- 停止並移除容器與 volume，重新建立
- 等待 PostgreSQL 初始化並驗證 schema
- 重啟 API 容器並確認健康狀態
- 匯入官方規則與用戶自定義

`setup.sh` 同時會：

- 在腳本所在目錄產生 `.env` 檔（供 docker-compose 及 Python 腳本使用）
- 自動將 `source .env` 寫入 `~/.bashrc`，重開機後環境變數仍可用

---

## 備份與恢復

### 建立備份

```bash
cd ~/hls-kb/util/
python3 backup_restore.py backup
```

備份完成後輸出：

```
✓ 備份完成!

  文件: /home/ubuntu/hls-kb/util/backups/hls_kb_full_20260313_170359.sql
  大小: 107.2 KB

  內容:
    • projects                      0 條
    • hls_rules                   391 條
    • design_iterations             0 條
    • synthesis_results             0 條
    • rules_effectiveness           0 條

✓ 元數據: hls_kb_full_20260313_170359.json
```

備份目錄 `util/backups/` 自動建立，每次產生兩個檔案：

- `hls_kb_full_YYYYMMDD_HHMMSS.sql` — 完整 SQL dump
- `hls_kb_full_YYYYMMDD_HHMMSS.json` — 元數據（備份時間、各表記錄數等）

### 列出備份

```bash
python3 backup_restore.py list
```

### 恢復備份

```bash
python3 backup_restore.py restore backups/hls_kb_full_YYYYMMDD_HHMMSS.sql
```

恢復完成後輸出：

```
✓ 恢復完成!

  恢復後統計:
    • projects                     16 條
    • hls_rules                   391 條
    • design_iterations            34 條
    • synthesis_results            34 條
    • rules_effectiveness          28 條
```

> 恢復操作會覆蓋當前資料庫，執行前需輸入 `yes` 確認。

---

## 資料庫工具

### 重置資料庫（僅清空數據，保留 schema）

```bash
cd ~/hls-kb/util/

# 查看目前資料量
python3 reset_database.py --stats

# 清空所有數據（保留表格結構）
python3 reset_database.py
```

清空完成後輸出：

```
✓ 資料庫已重置!

  projects                           0 條記錄
  hls_rules                          0 條記錄
  design_iterations                  0 條記錄
  synthesis_results                  0 條記錄
  rules_effectiveness                0 條記錄

  資料庫為空,可以開始導入數據
```

> 若需完整重建（含 schema），請使用 `setup.sh`。

---

## 回滾機制

### 專案與迭代概要

**專案（Project）** 對應一個 HLS 設計目標，以唯一的 `project_name` 識別，儲存於 `projects` 表。同一個設計目標的所有優化嘗試皆歸屬於同一個專案。

**迭代（Iteration）** 是該專案下的一次完整優化嘗試，迭代後會產生 HLS 程式碼、 Cursor 設計推論過程知識，規則統計及 Vitis-HLS 合成結果，以 `iteration_number`（1, 2, 3…）順序編號，儲存於 `design_iterations` 與 `synthesis_results` 表。

> 詳情見後續系統功能的設計迭代記錄與自動化。

### 回滾工具

用於移除迭代記錄，分兩階段執行：

**logger：** 從資料庫讀取迭代的 `_rollback_info` 快照，產生 YAML 回滾日誌（存於 `util/logs/`）。此階段不異動資料庫。

**rollback：** 讀取日誌，在單一交易中還原規則統計、刪除合成結果與迭代記錄。任一步驟失敗，資料庫回到執行前的狀態，支援 `--dry-run` 預覽。

`_rollback_info` 由 `complete_iteration` 寫入時自動附帶，可以精確還原 `rules_effectiveness` 統計值，並刪除 `synthesis_results` 與 `design_iterations`；若迭代缺少 `_rollback_info`  則只能直接刪除後兩者。`logger-rollback.py` 僅限系統管理員在 KB 主機（HLS01）上執行。

### 生成回滾日誌

```bash
cd ~/hls-kb/util/

# 生成特定迭代的回滾日誌
python3 logger-rollback.py logger --project FIR_Demo --iteration 3
```

```
[✓] Connected to database
[✓] Rollback log created: logs/rollback_FIR_Demo_iter3_20260328_190004.yaml
[✓] Iterations to rollback: 1
[✓] With _rollback_info: 1  |  Without: 0
[✓] Total rules_effectiveness operations: 3
[✓] Database connection closed
```

重點說明：

* `With _rollback_info: 1 | Without: 0` — 所有迭代均具備精確還原元資料，可還原規則統計值；若為 0 則只能刪除記錄，無法還原統計
* `Total rules_effectiveness operations: 3` — 回滾時將對 `rules_effectiveness` 執行 3 筆操作
* 此時尚未異動資料庫，日誌僅供下一階段 `rollback` 指令讀取

### 執行回滾

```bash
# 預覽（不實際執行）
python3 logger-rollback.py rollback --dry-run logs/rollback_FIR_Demo_iter3_20260328_190004.yaml

# 執行回滾
python3 logger-rollback.py rollback logs/rollback_FIR_Demo_iter3_20260328_190004.yaml
```

```
[✓] Connected to database
======================================================================
  ROLLBACK SUMMARY (v1.0 - Precise)
======================================================================
  Project: FIR_Demo
  Project ID: 10547eba-9e6d-409e-8642-05435c41708c
  Type: fir
  Date: 2026-03-28
  Iterations to rollback: 1
    - iter#3: UNROLL×4 MAC + ARRAY_PARTITION complete delay_line  [✓ precise]
      rules_effectiveness: 3 UPDATE(restore) + 0 DELETE(new)
======================================================================
Proceed with rollback? [y/N]: Y
[✓] Starting rollback transaction...
--- Iteration #3 ---
  [✓] RESTORED rules_effectiveness 333574eb... (applied=1, success=1)
  [✓] RESTORED rules_effectiveness 0460a7d4... (applied=2, success=2)
  [✓] RESTORED rules_effectiveness ca3548d7... (applied=2, success=2)
  [✓] DELETED synthesis_results b1d17254...
  [✓] DELETED design_iterations e40a3eee...
--- Project cleanup ---
  [!] Project 10547eba... kept: 2 iteration(s) still exist
[✓] Transaction completed successfully
[✓] Log file updated: logs/rollback_FIR_Demo_iter3_20260328_190004.yaml
[✓] Database connection closed
[✓] Rollback completed successfully
```

重點說明：

* `[✓ precise]` — 具備 `_rollback_info`，規則統計可精確還原（而非只刪除）
* `rules_effectiveness: 3 UPDATE(restore) + 0 DELETE(new)` — 表示 3 條規則在 iter#3 之前已有歷史記錄需還原，沒有因為 iter#3 而首次被套用的新規則
* `RESTORED rules_effectiveness 333574eb... (applied=1, success=1)` — 移除 iter#3 後，規則 `333574eb` 的套用次數還原為 1、成功次數還原為 1
* `[!] Project 10547eba... kept` — FIR_Demo 仍有 2 筆其他迭代，保留專案；若無剩餘迭代則改為 `DELETED project`
* `Log file updated` — YAML 日誌追加寫入 `rollback_status: completed`，作為操作留存記錄

---

## 使用者工作流程

### 1. Vitis-HLS 機器上的使用者目錄

> `cursor2hls` 為範例帳號名稱，可依實際情況建立並替換為對應的使用者帳號。

**位置**: `/home/cursor2hls/`

```
/home/cursor2hls/
└── cursorwork/                           # GitHub 複製目錄（亦為 Cursor workspace 根目錄）
    ├── .cursor/
    │   └── rules/                        # Cursor 規則目錄（由 generate-mdc.sh 產生）
    │       ├── hls-core.mdc              # 分類 1–5，alwaysApply: true
    │       ├── hls-code-standards.mdc    # 分類 6，alwaysApply: true
    │       └── hls-recording.mdc         # 分類 7，alwaysApply: true
    ├── hls-core.mdc-template             # 核心規則範本
    ├── hls-code-standards.mdc-template   # 程式碼快照規則範本
    ├── hls-recording.mdc-template        # 迭代記錄規則範本
    ├── hls-env.conf                      # 環境設定檔（主機、IP、DB、Vitis 路徑）
    └── generate-mdc.sh                   # 從模板產生 .mdc 規則的腳本
```

### 2. 在 Vitis-HLS 機器上建立 Cursor 規則（.mdc）

Cursor 規則由 `cursorwork/` 目錄中的三個 `.mdc-template` 與 `hls-env.conf` 合併產生，輸出至 `cursorwork/.cursor/rules/`。

**步驟 1：確認 `hls-env.conf` 設定正確**

```bash
cat ~/cursorwork/hls-env.conf
```

`hls-env.conf` 完整內容如下，根據實際環境修改後儲存：

```bash
# ============================================================================
# HLS 實驗室環境設定
# ============================================================================
# 用途：定義知識庫主機、網路、工具與 FPGA 目標
# 使用：./generate-mdc.sh 讀取此檔案以產生 .cursor/rules/*.mdc
# 格式：KEY=VALUE
# 說明：以 # 開頭的行為註釋
# ============================================================================

# --- 知識庫主機 (Knowledge Base Host) ---
KB_HOST_NAME=HLS01
KB_HOST_IP=192.168.1.11
KB_API_PORT=8000

# --- 數據庫連接 (Database) ---
# （預設值，未修改安裝設置則無需更改）
DB_USER=hls_user
DB_PASS=hls_user_passwd
DB_NAME=hls_knowledge
DB_PORT=5432

# --- Vitis HLS 工具 (Tool) ---
VITIS_HLS_SETTING_PATH=/tools/Xilinx/Vitis_HLS/2023.2/settings64.sh
VITIS_HLS_CMD=vitis_hls

# --- FPGA 預設目標 (Default FPGA Target) ---
TARGET_PART=xc7z020clg400-1
DEFAULT_CLOCK_PERIOD_NS=10
```

**步驟 2：執行產生腳本**

```bash
cd ~/cursorwork/
chmod +x ./generate-mdc.sh
./generate-mdc.sh
```

腳本讀取 `hls-env.conf`，將三個 `.mdc-template` 中所有 `{{變數}}` 替換為實際值，輸出三個 `.mdc` 至 `.cursor/rules/`：

```
╔══════════════════════════════════════════════════════════╗
║  generate-mdc.sh                                         ║
╚══════════════════════════════════════════════════════════╝

KB Host:     HLS01 (192.168.1.11)

--- 產生當下環境 ---
主機名:     HLS02
IP 地址:    192.168.1.12
Vitis HLS:  ✓ 已安裝 (/tools/Xilinx/Vitis_HLS/2023.2/bin/vitis_hls)
KB API:     http://192.168.1.11:8000

輸出目錄:   /home/cursor2hls/cursorwork/.cursor/rules

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
處理: hls-core.mdc-template
  → .cursor/rules/hls-core.mdc
  ✓ {{KB_HOST_NAME}} → HLS01 (8 處)
  ✓ {{KB_HOST_IP}} → 192.168.1.11 (9 處)
  ...
  ✓ 替換完成（412 行）
...
✓ 全部完成！沒有殘留的 {{變數}}

產生檔案：
  hls-core.mdc              461 行  28K
  hls-code-standards.mdc    467 行  20K
  hls-recording.mdc         676 行  40K
```

> HLS03 同樣需要登入後重複步驟 1～2，產生屬於 HLS03 的 `.mdc` 規則檔。

### 3. 安裝 Cursor（Windows 端）

前往 [Cursor 官網](https://cursor.com/download) 下載 **Windows (x64) (System)** 版本，執行安裝程式完成安裝。

### 4. 連接 Vitis-HLS 機器（Cursor Remote SSH）

以下步驟以 HLS02 為範例說明使用者端的設置流程，HLS03 重複相同步驟即可。

在 Cursor 中安裝 **Remote - SSH** 擴展，新增 SSH Host：

```
Host Vitis-HLS02-Server
    HostName hls-external-ip
    User cursor2hls
    Port 1200
```

連線後，在 Cursor 中開啟 `~/cursorwork/` 作為 workspace（File → Open Folder → 選擇 `/home/cursor2hls/cursorwork`）。

> Cursor 的 `.mdc` 規則必須位於 `cursorwork/.cursor/rules/`。若開啟 `~/`（家目錄），Cursor 會在 `~/.cursor/rules/` 尋找規則，找不到產生的 `.mdc` 檔案。

**確認規則已生效：** 在 Cursor 對話框輸入 `What rules are you following?` 或 `Summarize your active Cursor rules`。三份規則均設為 `alwaysApply: true`，在 Cursor 對話框詢問時應能同時看到全部三份規則摘要。

### 5. 連接知識庫（DBeaver + SSH 隧道）

管理者與使用者皆可使用 DBeaver 連接知識庫，方便直接管理及檢視透過 Cursor 自動化寫入的迭代記錄、合成結果與規則應用統計。

**步驟 1：下載並安裝 DBeaver（Windows）**

前往 [DBeaver Community](https://dbeaver.io/download/) 下載 **Community Edition** Windows 安裝程式，執行後依預設設定完成安裝。

**步驟 2：依網路環境選擇連線方式**

根據 Windows 機器目前的網路環境，選擇對應的連線方式：

**情況 A：未在公司內網且未連公司 VPN（需建立 SSH 隧道）**

Windows 在外網時無法直接存取內網的 HLS01（`192.168.1.11`），需透過具外網 Port Forwarding 的 HLS02 作為跳板，建立 SSH 隧道將流量轉送至 HLS01 的 PostgreSQL。

在 Windows 命令提示字元（cmd）中執行：

```cmd
ssh -L 5432:192.168.1.11:5432 cursor2hls@hls-external-ip -p 1200
```

此指令說明：

- `-L 5432:192.168.1.11:5432`：將本機 `localhost:5432` 透過隧道對應至 HLS01 的 `192.168.1.11:5432`
- `cursor2hls@hls-external-ip -p 1200`：透過 HLS02 的外網 Port Forwarding（port 1200）建立 SSH 連線作為跳板

輸入密碼後保持此視窗開啟，關閉即中斷隧道連線。DBeaver 連線主機填 `localhost`，端口填 `5432`。

**情況 B：已在公司內網或已連上公司 VPN（直接連線）**

無需建立 SSH 隧道。DBeaver 連線主機直接填 `192.168.1.11`，端口填 `5432`。

**步驟 3：在 DBeaver 中新增連線**

開啟 DBeaver，點擊「新建資料庫連線」（`Ctrl+Shift+N`），選擇 PostgreSQL，依情況填入主機與端口後，其餘欄位如下：

- **資料庫（Database）**：`hls_knowledge`
- **用戶名（Username）**：`hls_user`
- **密碼（Password）**：`hls_user_passwd`

> **帳號說明**：DBeaver 使用帳號（`hls_user`）連線，僅供查看資料；管理員帳號（`admin`）才具備修改資料權限。

點擊「測試連線」，首次連線會提示下載 PostgreSQL 驅動，點擊「下載」後再點「完成」。

---

## 系統功能

### 雙軌查詢策略

Cursor AI 在開始每次設計前會自動進行雙軌查詢，順序如下：

**Track 1（優先）**：呼叫 `/api/design/similar` 了解同類型專案的性能上限與最佳優化技術組合（含 pragma、方法描述、及 cursor_reasoning 推理過程），按 ii_achieved 排序。記錄 `pragmas_used` 供 Track 2 去除重複，記錄 `iteration_id` 供必要時查詢完整程式碼與詳細上下文。

```bash
curl "http://localhost:8000/api/design/similar?project_type=fir&limit=10"

# 必要時查詢最佳迭代完整程式碼（approach 描述不夠具體，或最佳 II 與當前差距很大時）
curl "http://localhost:8000/api/design/{iteration_id}/code"
```

**Track 2**：先呼叫 `/api/rules/categories` 取得 Category 清單（供後續各步共用，不需重複呼叫），再依以下流程查詢：

```bash
curl "http://localhost:8000/api/rules/categories"
```

**步驟 0（可選）：應用類 category 優先**

若從 `USER_SPEC`、用戶訊息或已知 `project_type` 能明確推斷出應用類型 `T`（如 `fir`、`systolic`），且 `categories` 清單中包含相同字串，則在進入技術面向 category 查詢前，先查詢應用類規則納入本輪候選：

```bash
curl "http://localhost:8000/api/rules/effective?category=${T}&project_type=${T}&min_success_rate=0"
```

若 `categories` 不含 `T` 或無法合理推斷，跳過步驟 0。無論步驟 0 是否執行，仍須依 Track 1 結果走路徑 A 或路徑 B，補齊技術面向規則；應用類與技術面向規則合併為本輪候選，不互相覆蓋。

**路徑 A — Track 1 有相似專案**：從 Track 1 的 `approach_description`、`pragmas_used`、`cursor_reasoning` 推論最相關的技術 Category（可 > 1），與步驟 0 的應用類規則合併為候選。先以 `rule_text` 語意篩選；若語意無符合，fallback 至統計篩選（`success_count > 0` → 按 `times_applied DESC`；`success_count = 0` → 按 `priority DESC`）。Track 1 中已出現的 pragma 對應規則標記為「已知有效」，不重複推薦。

```bash
curl "http://localhost:8000/api/rules/effective?category={inferred_category}&min_success_rate=0"
```

**路徑 B — Track 1 無相似專案（從零開始）**：Cursor 根據問題特性推論優先與候選 Category，依序 fallback 查詢，前一步語意篩選有符合結果即停止；應用類規則（步驟 0）與技術面向規則合併，不互相覆蓋：

- **步驟 2-1：優先 Category** — 語意篩選；無符合 → fallback 統計（`success_count > 0` → `times_applied DESC`；`= 0` → `priority DESC`，優先 priority=9）
- **步驟 2-2：候選 Category（2-1 完全無結果時觸發）** — 同上
- **步驟 2-3：不分 Category × priority=9（2-1 與 2-2 皆為空時觸發）** — 取 HLS 基本原則規則（priority=9，適用任何設計）

```bash
# 步驟 2-1 / 2-2
curl "http://localhost:8000/api/rules/effective?category={category}&min_success_rate=0"
# 步驟 2-3
curl "http://localhost:8000/api/rules/effective?min_success_rate=0"
# Cursor 過濾：priority = 9
```

> **API 參數說明**：`/api/rules/effective` 僅支援 `project_type`、`category`、`rule_type`、`min_success_rate` 四個參數。`times_applied`、`success_count`、`priority` 的篩選與排序，以及 `rule_text` 語意比對，均由 Cursor 在收到回傳結果後自行處理。

#### 規則 Priority

規則匯入時依規則文字的關鍵字自動設定 priority：

| Priority | 觸發關鍵字                                    | 語意        |
| -------- | ---------------------------------------- | --------- |
| 9        | `always`, `must`, `critical`, `never`    | 強制性、不可違反  |
| 7        | `do not`, `avoid`, `ensure`, `should`    | 強烈建議、應避免  |
| 5        | `consider`, `may`, `recommend`, `prefer` | 建議性、可選擇   |
| 4        | （無符合關鍵字）                                 | 預設值，一般性規則 |

兩軌結果綜合後，Cursor AI 提出優化方案並於設計中精確引用規則編號（R### / P###），在`complete_iteration`階段會自動將本次應用的規則回寫至 `rules_effectiveness` 更新成功率統計。

#### 規則分類機制

兩個規則檔案均以 `# Category: <名稱>` 標注分類，`import_rules.py` 直接讀取此值寫入資料庫，category 完全由人工標注決定。

```
# Category: dataflow        ← 以下規則歸入此 category
- [R001] Always use #pragma HLS DATAFLOW ...
- [R002] Ensure producers and consumers ...
```

`rules_ug1399.txt` 與 `rules_user_defined.txt`，兩個檔案均可自由新增新 category。`import_rules.py` 無需修改即可支援。

#### 人工標注的 Category

`rules_user_defined.txt` 為使用者自定義規則檔案，可包含技術面向 category 如 `pipeline`、`memory`，也可包含應用相關 category 如 `fir`、`systolic`、`cordic`。以實際分類為例：

| Category   | 說明                | 範例規則                                                       |
| ---------- | ----------------- | ---------------------------------------------------------- |
| `pipeline` | 流水線化與 II 優化       | P011 `PIPELINE II=1 rewind`、P018 禁止 innermost loop 純量累加    |
| `memory`   | 陣列存取與分割           | P033 禁止 hot loop 中存取 off-chip、P037 對展開的 lane 個別分割陣列        |
| `fir`      | FIR 濾波器應用優化       | P068 合併移位與計算迴圈消除依賴、P069 加 `rewind` 使相鄰迭代無縫重疊               |
| `systolic` | Systolic array 架構 | P083 以 next-state 陣列消除 RAW hazard、P086 輸入時序 skew 對齊各 PE 資料 |

`pipeline`、`memory` 等技術 category 在 `rules_ug1399.txt`與`rules_user_defined.txt` 都有。  `fir` 與 `systolic` 是應用層 category，僅在 `rules_user_defined.txt`，API 查詢時自動合併回傳不分 official / user_defined。

在 Track 2 步驟 0，Cursor 根據使用者輸入推論 category，再呼叫 `/api/rules/effective?category=<名稱>` 精準取得對題規則：

```
使用者輸入「FIR 濾波器，目標 II=1」
  → Cursor 推論 category：fir、pipeline
  → GET /api/rules/effective?category=fir      ← P068-P070 迴圈合併/rewind 技巧
  → GET /api/rules/effective?category=pipeline ← R035-R037 + P011-P024 流水線規則
  → 精準取得對題規則，略過 systolic / interface 等無關 category
```

> **命名建議**：技術面向用通用名稱（`pipeline`、`memory`）；應用專屬用應用名稱（`fir`、`systolic`、`cordic`）。`project_type` 追蹤的是「這個專案是什麼」，category 追蹤的是「這條規則屬於哪種優化」，兩者不同。

查詢規則：

```bash
# 統一查詢（推薦）：按 category + effectiveness 篩選，不分 official / user_defined
curl "http://localhost:8000/api/rules/effective?category=pipeline&min_success_rate=0"

# 特定 project_type 的所有規則（Cursor 端先以 rule_text 語意篩選，再按 success_count / times_applied / priority 排序）
curl "http://localhost:8000/api/rules/effective?project_type=fir"

# 瀏覽用途：按 rule_type 過濾（非工作流程必要）
curl "http://localhost:8000/api/rules/effective?rule_type=official&min_success_rate=0"
curl "http://localhost:8000/api/rules/effective?rule_type=user_defined&min_success_rate=0"
```

> **`project_type` 過濾行為**：統計範圍限定於指定的 `project_type`。從未套用於該類型的規則仍會出現在結果中，`times_applied=0`，不會被排除。

### 設計迭代記錄與自動化

每次 Cursor Agent 執行 HLS 任務前，會先自動驗證當前環境確認 HLS 機器環境及 API 連結，確保後續 API 呼叫路由正確。合成完成後，Step 9 的 `complete_iteration` API 在單次呼叫中同時完成迭代記錄、合成結果寫入、`rules_effectiveness` 更新，並於 `reference_metadata` 中寫入 `_rollback_info` 快照（支援精確回滾）與 `_rules_applied` 快照（結構化記錄本次套用的規則）；Step 10 的本地 Markdown 備份則確保即使 API 不可用，設計記錄也不遺失。

**觸發條件**：`csim`（功能驗證）**且** `csynth`（高層次合成）**兩者都成功**後，Cursor AI 自動執行後半段流程（Step 7–10）。任一失敗則停止，不記錄該迭代：

> ❗ **header comment 寫入時機**：Cursor 寫代碼時 .cpp **不含** file header comment，只寫代碼本體與每個 `#pragma HLS` 上方的三行 pragma comment。csim + csynth 都成功後，解析報告取得實測數據，再將完整 header comment 一次插入 .cpp 最頂端（所有 `#include` 之前），然後才組裝 code_snapshot 寫入 KB。header 中所有數值（Synthesis Result、Resources、每個 Optimization 的 Result）均為實測值。

| 步驟      | 操作                                                                                  |
| ------- | ----------------------------------------------------------------------------------- |
| Step 1  | Front-Capture：掃描用戶訊息，維護 USER_REF_CODE / USER_SPEC                                   |
| Step 2  | 雙軌查詢：以 `/api/design/similar` 查詢相似設計（Track 1），以 `/api/rules/effective` 取得規則（Track 2） |
| Step 3  | Bind Rules：綁定選定規則至 APPLIED_RULES；推理脈絡記入 `cursor_reasoning`                          |
| Step 4  | 提出優化方案（根據 KB 知識與用戶輸入）                                                               |
| Step 5  | 寫代碼 + pragma comment（每個 `#pragma HLS` 上方三行說明；**此時不寫 file header comment**）          |
| Step 6  | 執行 csim + csynth（任一失敗 → 停止，不記錄）                                                     |
| Step 7  | 解析 csynth 報告（II、Latency、Resources、Timing），一次填入完整 header comment（實測值）                |
| Step 8  | 用 `/api/projects` + `project_name` 精確比對取得 `project_id`（**關鍵**，避免重複建立專案）             |
| Step 9  | 呼叫 `POST /api/design/complete_iteration`                                            |
| Step 10 | 建立 / 更新本地 markdown 文檔備份                                                             |
| Step 11 | 若 II 未達標，以本次結果為基礎更新 `previous_ii`，從尚未嘗試的 pragma 組合選取最佳方案，回到 Step 2 重新迭代             |

> **Step 7 Applied Rules 記錄規則**：凡 Cursor 推論優化方向時有參考或應用的規則，無論能否確認 rule_code，都必須記錄在 `code_snapshot` header 的 Applied Rules 段落。有 rule_code 時寫 `P###/R###: rule_text`；無法確認 rule_code 時寫純 rule_text，不得省略。

### 重現指定迭代

當需要驗證歷史迭代結果，或以某個歷史迭代作為新優化的起點時，透過以下步驟重現。重現僅用於驗證或學習，不觸發自動記錄流程（code_snapshot 與原始記錄相同，記錄會產生重複資料）。

**Step 1：取得目標 iteration_id 與 project_id**

```bash
# A. 用戶指定 project 及 iteration number
curl "http://localhost:8000/api/analytics/project/${PROJECT_ID}/progress"
# B. 依 project_type 從最佳設計查詢
curl "http://localhost:8000/api/design/similar?project_type=fir&limit=10"
# 兩者都會回傳 iteration_id 和 project_id
```

**Step 2：取回完整 code_snapshot 並還原檔案**

```bash
curl "http://localhost:8000/api/design/${ITER_ID}/code"
# 回傳：code_snapshot、approach_description、code_hash、pragmas_used、
#       user_specification、cursor_reasoning、prompt_used、user_reference_code
```

從 code_snapshot 中按分隔行（`// === {filename} ===`）拆分還原為實際檔案。檔案順序為 [.h] → .cpp → testbench → [.inc]。`.inc` 檔從 code_snapshot 還原後放在與 .cpp 相同目錄（不需在 run_hls.tcl 中 add_files）。

**Step 3：取得環境參數並產生 run_hls.tcl**

code_snapshot 不包含 `run_hls.tcl`，需根據還原的檔案資訊自動產生：

- **top function**：從 code_snapshot 的函式簽名推斷（如 `void fir(...)` → `set_top fir`）
- **add_files**：從分隔行取出所有 filename，過濾掉 `*_tb.cpp` 與 `*.inc` 後，先加 `.h`（若有），再加 `.cpp`
- **testbench**：從分隔行中取 `*_tb.cpp` filename，以 `add_files -tb` 加入
- **.inc files**：不需 `add_files`；從 code_snapshot 還原後放在與 .cpp 相同目錄（由 .cpp 以 `#include "*.inc"` 引用）
- **target_device**：使用 `hls-env.conf` 的 `TARGET_PART` 設定值（已由 `generate-mdc.sh` 填入規則）
- **clock_period**：使用 `hls-env.conf` 的 `DEFAULT_CLOCK_PERIOD_NS` 設定值（已由 `generate-mdc.sh` 填入規則）

**Step 4：重跑合成並驗證**

```bash
source /path/to/settings64.sh
vitis_hls -f run_hls.tcl   # 執行 csim_design + csynth_design
```

重現完成後，比對 II、Latency、Resources 是否與原始記錄一致。code_snapshot 的 header comment 包含完整實測數據（Synthesis Result、Resources），可直接從 header 取值比對，無需額外查詢 KB `synthesis_results`。若重現結果與原始記錄不一致，可能原因為 Vitis HLS 版本不同或 FPGA target 不同。

### 知識庫存取原則（多人共用）

知識庫由所有 Cursor HLS 使用者共用，`rules_effectiveness` 的成功率統計會影響每位使用者的規則推薦結果，因此採用以下存取原則：

| 操作類型                             | 執行者                       | 說明                            |
| -------------------------------- | ------------------------- | ----------------------------- |
| 查詢規則 / 設計                        | Cursor HLS 使用者            | 隨時可查，不影響共用資料                  |
| 寫入新 iteration                    | Cursor HLS 使用者            | 僅透過 `complete_iteration` 自動完成 |
| 更新規則統計                           | `complete_iteration` 自動執行 | 由 API 內部在交易中更新，無獨立端點          |
| Rollback（移除 Project 或 iteration） | 系統管理員                     | 需系統管理權限                       |
| 知識庫備份 / 恢復 / 重置                  | 系統管理員                     | 需系統管理權限                       |

**並發寫入安全**：多位使用者同時使用知識庫時，API 已內建防碰撞機制。若建立專案時發現同名專案已存在，API 回傳 **409 Conflict** 及 `existing_project_id`；Cursor 取出該 ID 重新呼叫 `complete_iteration`，不需要使用者介入。

### API 端點服務

Cursor AI 依設計階段自動呼叫對應端點——設計前以 `/api/design/similar` 查詢相似設計案例（學習最佳優化方法）、以 `/api/rules/categories` 取得 Category 清單、以 `/api/rules/effective` 取得規則（Cursor 端先以 `rule_text` 語意篩選對題規則，再按 success_count / times_applied / priority 排序）；合成後依自動記錄設計迭代先取得 `project_id`，再以 `/api/design/complete_iteration` 一次完成所有資料寫入（`iteration_number` 由 API 自動計算）；如需查看專案的迭代則呼叫 `/api/analytics/.../progress`。整個流程由 Cursor Agent 自動串接，使用者無需手動執行任何 API 呼叫。

| 端點                                             | 方法   | 說明                                                                                                       |
| ---------------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------- |
| `/health`                                      | GET  | 健康狀態檢查                                                                                                   |
| `/api/projects`                                | GET  | 列出所有專案（支援 type, limit, offset）                                                                           |
| `/api/projects`                                | POST | 建立新專案（並發寫入安全）                                                                                            |
| `/api/projects/{project_id}`                   | GET  | 取得單一專案詳情                                                                                                 |
| `/api/design/similar`                          | GET  | 查詢相似設計（學習用，含 cursor_reasoning；不含 code_snapshot / prompt_used / user_reference_code / reference_metadata） |
| `/api/design/{iteration_id}/code`              | GET  | 取得特定迭代的完整詳細資訊（code_snapshot、cursor_reasoning、prompt_used、user_reference_code；**不含 reference_metadata**）  |
| `/api/rules/effective`                         | GET  | 查詢規則（支援 rule_type 過濾，預設 min_success_rate=0.0）                                                            |
| `/api/rules/categories`                        | GET  | 回傳所有 Category 清單（供雙軌查詢 Category 推論使用）                                                                    |
| `/api/design/complete_iteration`               | POST | 完整記錄一次迭代                                                                                                 |
| `/api/analytics/project/{project_id}/progress` | GET  | 傳回該專案所有的迭代結果                                                                                             |
| `/docs`                                        | GET  | Swagger UI 互動文檔                                                                                          |

> 記錄迭代前必須透過設計迭代記錄與自動化 **Post-Synthesis** 取得 `project_id`，禁止從 `/api/design/similar` 結果取用——`similar` 按性能排序，排首的專案可能屬於其他人。

> `rules_effectiveness` 的更新只由 `complete_iteration` 在交易中自動完成。

**各端點的詳細請求/回應格式、完整操作範例與端對端工作流程，請參閱 API 詳細範例與操作指南**。

## 障礙排除

**DBeaver 無法連線資料庫**

情境：DBeaver 顯示連線逾時或拒絕連線。常見原因及排查順序：

1. **SSH 隧道中斷**：長時間閒置或網路切換後隧道會自動斷開。在 Windows CMD 重新建立隧道：
   
   ```bash
   ssh -L 5432:192.168.1.11:5432 cursor2hls@hls-external-ip -p 1200
   ```

2. **PostgreSQL 服務未啟動**：SSH 到知識庫主機後執行 `docker ps` 確認 PostgreSQL 容器狀態為 `Up`；若未啟動，在 `~/hls-kb/` 執行 `docker compose up -d`

**Cursor 回報權限不足或無法執行指令**

情境：Cursor 提示 permission denied 或指令無回應。常見原因：

1. **Cursor 處於 Ask 模式**：Ask 模式下 Cursor 只能回答問題，無法執行終端指令。使用者需在 Cursor 介面切換至 Agent 模式後再執行 HLS 任務
2. **SSH 連線中斷**：Cursor Remote SSH 長時間閒置後可能斷線。重新開啟 Cursor 的 Remote SSH 連線至目標 Vitis-HLS 主機

---

**版本**: v1.0 

**最後更新**: 2026-03-28

---

## 銘謝

本專案的完成，謹向以下人士與單位致上誠摯謝意：

**Jiin Lai** 教授及其研究團隊  
國立清華大學（National Tsing Hua University）  
感謝在 HLS 設計方法論與研究議題方面給予的寶貴指導。

**Eric Chang** 及 AMD Xilinx 團隊  
感謝在 Vitis HLS 技術方面提供的專業建議與資源支援。
