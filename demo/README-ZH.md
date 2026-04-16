# HLS Knowledge Base — 範例導引指南

[English](./README.md) | 中文

---

> **項目名稱**: cursor-hls-kb **版本**: v1.0
> 
> **目標讀者**: Cursor HLS 使用者(新手與規則貢獻者)

---

## 目的

本指引透過 KB 隨附的 6 個範例專案,說明知識庫在實務使用中的運作方式。範例皆為實際的 Cursor + Vitis HLS 設計過程,非簡化的教學案例。

讀完本指引後,讀者可以:

- 從 KB 回傳的內容,判斷一個新設計能否在 iter 1 達到 II=1
- 識別何時需要由使用者提供架構引導,以及這類引導如何轉化為後續的 P-rule
- 為自己的情境選擇合適的入門範例

---

## 兩種使用模式

6 個範例可依「KB 中是否已累積該類設計的成熟 P-rules」分為兩類。這個區分有助於預估使用 KB 時的迭代次數。

### 模式 A — 已有成熟 P-rules,規格性提示即可

| 範例            | 取得的 P-rules (Track 2)              | iter 1 結果             | 提示風格                                   |
| ------------- | ---------------------------------- | --------------------- | -------------------------------------- |
| **Systolic**  | 5 條 (P085, P084, P090, P094, P047) | II=1,僅需放寬 timing      | 「設計 systolic array... follow KB rules」 |
| **Matmul3x3** | 3 條 (P047, P035, P039)             | II=1(clock 放寬至 20 ns) | FIFO 介面 + 矩陣尺寸                         |
| **FIR128**    | 2 條 (P047, P079)                   | II=1,12 ns timing 通過  | 「AXI streaming,最小化面積」                  |
| **CORDIC**    | 2 條 (P071, P072)                   | II=1, 0 DSP           | 算法規格(模式、定點數、迭代數)                       |

模式 A 中,先前的測試已將該類設計的 HLS 架構決策(`PIPELINE` 的位置、陣列 partition 方式、stream I/O 的限制)整理為 P-rules。使用者描述設計目標,Cursor 結合 KB 規則完成優化。

### 模式 B — P-rules 較少,需要架構引導,過程中產出新規則草案

| 範例             | 取得的 P-rules (Track 2) | iter 1 結果                | 使用者提供                                     |
| -------------- | --------------------- | ------------------------ | ----------------------------------------- |
| **DFT (16 點)** | 1 條 (P003)            | II=1,timing 失敗(−0.84 ns) | iter 2-4 提供 II/timing 取捨方向                |
| **FFT (16 點)** | 1 條 (P035)            | 25 ns 下 II=2,未達 II=1     | iter 2 提供 ping-pong、template banks、MAC 拆解 |

模式 B 中,KB 對該類設計累積的規則有限。使用者需透過後續提示引導架構決策。每個成功的引導會以草案規則的形式寫入檔案 header 的 `Applied Rules` 區塊,後續由 KB 管理者升級為編號的 `P###`。

```cpp
// Applied Rules (FFT_Demo iter2):
//  - R035: inner loops use #pragma HLS PIPELINE
//  - P035: no full-buffer memcpy between stages
//  - (no code): when a single loop iteration writes to the same logical
//               array twice, use complete partition or dual-port memory
//               to avoid a carried dependence forcing II>1.
//  - (no code): prefer ping-pong buffering over in-place updates for
//               multi-stage pipelined algorithms.
```

DFT 產出 3 條草案規則,FFT 產出 4 條。經審核編號後,後續同類設計即可進入模式 A 的流程。

---

## 知識回饋循環

KB 的規則庫透過兩個階段的循環逐步擴充:模式 B 在迭代除錯中產出草案規則,經 KB 管理者審核後升級為 `P###`;後續同類設計即可進入模式 A,使用者透過規格描述就能讓 iter 1 達到 II=1。

**模式 B(規則尚未建立)**
新設計類別,KB 中 P-rules 很少 → 使用者後續提示提供架構引導 → iter 2+ 除錯,草案規則寫入檔案 header → KB 管理者審核,升級為 `P###`

↓ 新 P-rules 進入 KB ↓

**模式 A(規則已就緒)**
同類設計,已有成熟 P-rules → 使用者只提供規格描述 → iter 1 即達 II=1

換言之,某個專案在迭代過程中累積的優化經驗,可供後續同類設計直接使用,這是 KB 規則庫隨時間擴充的方式。

---

## 如何應用到自己的設計

1. 從規格性提示開始,描述設計的功能、介面與限制,結尾加上 `follow KB rules`
2. 觀察 Track 2 回傳的內容:P-rules 多通常是模式 A;P-rules 少或沒有則預期落入模式 B
3. 若 iter 1 即達 II=1 且 timing 通過,屬於模式 A,後續視需要再優化面積或吞吐
4. 若 iter 1 未達目標,屬於模式 B,下一輪提示一次調整一個架構參數(II 目標、pipeline 位置、資料相依性、partition 策略)
5. 成功的引導會以 `(no code)` 條目寫入檔案 header,累積一組值得正式化的草案後,通知 KB 管理者升級為 `P###`

> **為什麼模式 B 中建議「一次調整一個參數」**:HLS 優化結果與上下文相關,同一個 `complete partition` 在 systolic 設計中可達成 II=1,但用於 DFT iter 1 會導致 timing 失敗。每次只改一個變數,可保留因果關係的可追溯性,升級為正式規則時也較容易驗證。

---

## 範例索引

| 檔案                  | 領域                | 迭代  | 模式  | 重點                                             |
| ------------------- | ----------------- | --- | --- | ---------------------------------------------- |
| `demo_systolic.md`  | Systolic GEMM     | 3   | A   | 一次提示即 II=1;5 條 P-rules 涵蓋架構                    |
| `demo_matmul3x3.md` | 矩陣乘法              | 3   | A   | FIFO 介面;DATAFLOW 重疊 3 個矩陣                      |
| `demo_fir128.md`    | FIR 濾波器 (128 tap) | 3   | A   | 串流、BRAM 循環緩衝、2-way 並行 MAC                      |
| `demo_cordic.md`    | sin/cos           | 3   | A   | 純 shift-add(0 DSP);DATAFLOW 對比 PIPELINE 對比時間共用 |
| `demo_dft.md`       | DFT (16 點)        | 4   | B   | II 對 timing 的設計空間;產出 3 條草案規則                   |
| `demo_fft.md`       | FFT (16 點)        | 2   | B   | Ping-pong + template banks 達 II=1;產出 4 條草案規則   |

---

## 建議的閱讀順序

- **第一次使用 KB**:讀 `demo_systolic.md`,展示「一次提示 → II=1」的流程,並說明每條 P-rule 的作用
- **了解規則貢獻流程**:讀 `demo_fft.md`,呈現 4 條草案規則如何從具體的除錯回合(HLS warning 200-880、bank selection 上的 sparsemux 等)記錄到 `code snapshot` 的 file header comment，待升級為正式規則
- **觀察設計空間探索**:讀 `demo_dft.md`,4 次迭代涵蓋 II=1、timing、area 之間的取捨,包含「正式提交 iter 4 前先快速試跑驗證」的做法
- **比較不同優化風格**:讀 `demo_cordic.md`,同一算法的 3 種實作(DATAFLOW、單一 PIPELINE、時間共用)以合成數據呈現取捨

---

**版本**: v1.0 **最後更新**: 2026-04-16

---

*KB system: cursor-hls-kb v1.0 by AICOFORGE.*
