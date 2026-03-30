# HLS Knowledge Base — System Administration & User Guide

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![For Education](https://img.shields.io/badge/Use-Education%20%26%20Academic-green.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

> Copyright (c) 2026 AICOFORGE. All rights reserved.
> CC BY-NC 4.0 — non-commercial use only. See LICENSE.
> Commercial use: kevinjan@aicoforge.com
> 
> This Architecture, domain knowledge, and design decisions are original work by AICOFORGE.

---

[中文](./README-ZH.md) | English

---

> **Project Name**: cursor-hls-kb  
> **Version**: v1.0
> 
> **Target Audience**: KB Administrator / Cursor HLS User

---

## Features

- **Centralized Knowledge Base**: Stores HLS official rules (UG1399) and practical optimization experience in a centralized database, tracking the effectiveness of each rule
- **Cursor AI Automation**: Developers design on Vitis-HLS machines via Cursor Remote SSH; Cursor automatically queries best optimization cases during the design process, ensuring every decision is backed by the Knowledge Base, then writes iteration information, performance results, and applied rules to the Knowledge Base after synthesis
- **Precise Rollback Mechanism**: Uses `_rollback_info` metadata to precisely restore database state for specific iterations or entire projects, with rollback preview support
- **Lightweight API Access**: API service (port 8000) provides endpoints for rule queries, iteration recording, synthesis results, etc.; Cursor on Vitis-HLS machines calls via LAN directly, no additional deployment needed
- **Visual Data Inspection**: Both administrators and developers can view the database directly via DBeaver, making it easy to manage and inspect data written by Cursor automation

---

## Overview

This repository provides the infrastructure and tools for the HLS (High-Level Synthesis) Knowledge Base system, including database management, backup and restore, rollback mechanism, and Cursor AI collaborative design workflows.

---

## System Architecture

<p align="center">
  <img src="https://github.com/user-attachments/assets/a935fdda-f26c-41cb-a25e-06a191928c2f" width="70%">
</p>

**Access Methods**:

- **Cursor AI Agent** — Connects to the Vitis-HLS host via **SSH**, which then accesses the HLS Knowledge Base host's **FastAPI** service (port 8000) over the internal LAN to perform read/write operations.
- **DBeaver** — Connects to the Vitis-HLS host via **SSH Tunnel** or **Direct** connection, which then accesses the HLS knowledge base PostgreSQL server (port 5432) over the internal LAN. Administrators have read/write access, while Developers are restricted to read-only.

---

## Database Schema

### Tables (5)

| Table                 | Purpose                                              |
| --------------------- | ---------------------------------------------------- |
| `hls_rules`           | Rule definitions (R### official / P### user-defined) |
| `projects`            | Project information                                  |
| `design_iterations`   | Related information for each design iteration        |
| `synthesis_results`   | HLS synthesis results (II, latency, resources)       |
| `rules_effectiveness` | Rule application effectiveness tracking              |

### Views (2)

| View                         | Purpose                                                                                                     |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `rule_effectiveness_summary` | Rule success rate summary (dynamically computed)                                                            |
| `best_designs_by_type`       | Best design record (lowest ii_achieved) per project_type, for quick lookup of best design baseline per type |

---

## Machine Configuration

The example environment consists of 3 machines on the same LAN, accessible individually via public IP `hls-external-ip` using different port forwarding. The system administrator must first complete installation and initialization of the HLS01 Knowledge Base host (including PostgreSQL, FastAPI deployment, and rule import) before developers can retrieve data from the Knowledge Base when running Cursor automated HLS design on their Vitis-HLS hosts.

| Machine   | Role                | LAN IP (Example) | Public Port Forwarding (Example) | Description                                        |
| --------- | ------------------- | ---------------- | -------------------------------- | -------------------------------------------------- |
| **HLS01** | Knowledge Base Host | 192.168.1.11     | hls-external-ip:1100             | Administrator installed, runs PostgreSQL + FastAPI |
| **HLS02** | Vitis-HLS Host      | 192.168.1.12     | hls-external-ip:1200             | Vitis HLS installed, Cursor automated HLS design   |
| **HLS03** | Vitis-HLS Host      | 192.168.1.13     | hls-external-ip:1300             | Vitis HLS installed, Cursor automated HLS design   |

> Actual connection configuration can be adjusted based on environment; the network configuration above is for reference only.

---

## Administrator Quick Start

### Prerequisites

- **Operating System**: Ubuntu 22.04+ (recommended)
- **Docker**, **Docker Compose**, **Python 3**, **pip3**, **curl**, **asyncpg**, **pyyaml**

All packages above are automatically detected and installed by `env_setup.sh`. After execution, summary output:

```
==============================
 Environment Check Complete
==============================
curl             7.81.0
python3          3.10.12
docker           29.3.0
docker-compose   v5.1.0

[✓] Installation complete! Run the following command to apply docker group (one-time only):

    newgrp docker
```

How to run:

```bash
chmod +x ./env_setup.sh
sudo ./env_setup.sh
newgrp docker
```

### Administrator Directory

**Location**: `~/hls-kb/`

```
hls-kb/
├── kbapi.py                 # FastAPI service
├── init.sql.in              # Database schema source
├── init.sql                 # Generated by setup.sh (auto-created after execution)
├── docker-compose.yml       # Container orchestration (PostgreSQL + API)
├── Dockerfile               # API container image
├── requirements.txt         # Python dependencies
├── setup.sh                 # Setup script
├── import_rules.py          # Import rules (official rules + user-defined)
├── rules_ug1399.txt         # Official rules source
├── rules_user_defined.txt   # User-defined rules source
└── util/
    ├── backup_restore.py    # Backup and restore tool
    ├── logger-rollback.py   # Rollback tool
    └── reset_database.py    # Database clearing tool (does not rebuild schema)
```

### System Initialization

```bash
cd ~/hls-kb/
chmod +x ./setup.sh
./setup.sh
```

`setup.sh` defines environment variables at the top (database account, password, port, etc.). **Change the account and password to your own before first use**; other parameters (port, DB name, etc.) can be left at their defaults unless you have specific requirements.

```bash
# ==================== Environment Variable Definitions (edit this block directly) ====================
KB_API_PORT=8000
DB_HOST=localhost
DB_ADMIN=admin              # Admin account (used by KB host, read-write access)
DB_ADMIN_PASS=admin_passwd
DB_USER=hls_user            # General account (used by Vitis-HLS host, read-only access)
DB_PASS=hls_user_passwd
DB_NAME=hls_knowledge
DB_PORT=5432
# ======================================================================
```

> **Warning: Do not set `DB_USER` to `user`**, `user` is a PostgreSQL reserved keyword (SQL standard), and using it directly in `CREATE USER user ...` will cause a syntax error.

Output after `setup.sh` completion:

```
===========================================================
Final Verification
============================================================

Database Statistics:
  Official rules  (official):     287
  User-defined    (user_defined): 104
  ─────────────────────────────
  Total:                          391

API Test:
  Rules query: ✓

============================================================
✓ Initialization complete!
============================================================

Next step:
  Access API: curl http://localhost:8000/health
```

`setup.sh` main steps:

- Generates `init.sql` from `init.sql.in` via `sed`
- Stops and removes containers and volumes, then recreates
- Waits for PostgreSQL initialization and verifies the schema
- Restarts the API container and checks health status
- Imports official rules and user-defined rules

`setup.sh` also:

- Generates a `.env` file in the script directory (for use by docker-compose and Python scripts)
- Automatically adds `source .env` to `~/.bashrc`, so environment variables remain available after reboot

---

## Backup and Restore

### Create Backup

```bash
cd ~/hls-kb/util/
python3 backup_restore.py backup
```

Output after backup completion:

```
✓ Backup complete!

  File: /home/ubuntu/hls-kb/util/backups/hls_kb_full_20260313_170359.sql
  Size: 107.2 KB

  Contents:
    • projects                      0 record(s)
    • hls_rules                   391 record(s)
    • design_iterations             0 record(s)
    • synthesis_results             0 record(s)
    • rules_effectiveness           0 record(s)

✓ Metadata: hls_kb_full_20260313_170359.json
```

Backup directory `util/backups/` is auto-created; each backup produces two files:

- `hls_kb_full_YYYYMMDD_HHMMSS.sql` — Full SQL dump
- `hls_kb_full_YYYYMMDD_HHMMSS.json` — Metadata (backup time, record counts per table, etc.)

### List Backups

```bash
python3 backup_restore.py list
```

### Restore Backup

```bash
python3 backup_restore.py restore backups/hls_kb_full_YYYYMMDD_HHMMSS.sql
```

Output after restore completion:

```
✓ Restore complete!

  Post-restore statistics:
    • projects                     16 record(s)
    • hls_rules                   391 record(s)
    • design_iterations            34 record(s)
    • synthesis_results            34 record(s)
    • rules_effectiveness          28 record(s)
```

> Restore operation overwrites the current database; you must enter `yes` to confirm.

---

## Database Tool

### Reset Database (Clear Data Only, Preserve Schema)

```bash
cd ~/hls-kb/util/

# Check current data volume
python3 reset_database.py --stats

# Clear all data (preserving table structure)
python3 reset_database.py
```

Output after clearing:

```
✓ Database has been reset!

  projects                           0 record(s)
  hls_rules                          0 record(s)
  design_iterations                  0 record(s)
  synthesis_results                  0 record(s)
  rules_effectiveness                0 record(s)

  Database is empty, ready to start importing data
```

> For a full rebuild (including schema), use `setup.sh`.

---

## Rollback Mechanism

### Project and Iteration Overview

**Project** corresponds to a single HLS design goal, identified by a unique `project_name` and stored in the `projects` table. All optimization attempts for the same design goal belong to the same project.

**Iteration** is one complete optimization attempt under a project. Each iteration produces HLS source code, Cursor's design reasoning knowledge, rule effectiveness statistics, and Vitis-HLS synthesis results. Iterations are numbered sequentially (`iteration_number`: 1, 2, 3…) and stored in the `design_iterations` and `synthesis_results` tables.

> For details, see the Design Iteration Recording & Automation section under System Features.

Used to remove iteration records; executes in two phases:

### Rollback Tool

**logger**: Reads `_rollback_info` snapshots from the database and generates a YAML rollback log (stored in `util/logs/`). The database is not modified at this stage.

**rollback**: Reads the log and, within a single transaction, restores rule statistics and deletes synthesis results and iteration records. If any step fails, all executed operations are reverted and the database returns to its pre-execution state. Supports `--dry-run` for preview.

With `_rollback_info`: precisely restores `rules_effectiveness` statistics, and deletes `synthesis_results` and `design_iterations`. Without it: only the latter two are deleted. `_rollback_info` is automatically attached by `complete_iteration` at write time. `logger-rollback.py` must be executed on the KB host (HLS01) by the system administrator only.

### Generate Rollback Log

```bash
cd ~/hls-kb/util/

# Generate rollback log for a specific iteration
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

Key notes:

* `With _rollback_info: 1 | Without: 0` — all iterations have precise restoration metadata; rule statistics can be restored. if With `_rollback_info is 0`, those iterations can only be deleted without restoring statistics
* `Total rules_effectiveness operations: 3` — 3 operations will be executed against `rules_effectiveness` during rollback
* The database is not modified at this stage; the log is only used by the `rollback` command in the next phase

### Execute Rollback

```bash
# Preview (no actual changes)
python3 logger-rollback.py rollback --dry-run logs/rollback_FIR_Demo_iter3_20260328_190004.yaml

# Execute rollback
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

Key notes:

* `[✓ precise]` — `_rollback_info` is present; rule statistics can be precisely restored rather than just deleted
* `rules_effectiveness: 3 UPDATE(restore) + 0 DELETE(new)` — all 3 rules existed before iter#3 and will be restored to their prior statistics; `DELETE(new)` would apply to rules first introduced by this iteration (none in this case)
* `RESTORED rules_effectiveness 333574eb... (applied=1, success=1)` — after removing iter#3, rule `333574eb`'s times_applied is restored to 1 and success_count to 1
* `[!] Project 10547eba... kept` — FIR_Demo still has 2 other iterations and is retained; if no iterations remain, it would show `DELETED project`
* `Log file updated` — `rollback_status: completed` is appended to the YAML log as a permanent operation record

---

## Developer Workflow

### 1. Developer Directory on Vitis-HLS Machine

> `cursor2hls` is an example account name; create and replace with the appropriate user account as needed.

**Location**: `/home/cursor2hls/`

```
/home/cursor2hls/
└── cursorwork/                           # GitHub clone directory (also the Cursor workspace root)
    ├── .cursor/
    │   └── rules/                        # Cursor rules directory (generated by generate-mdc.sh)
    │       ├── hls-core.mdc              # Sections 1–5, alwaysApply: true
    │       ├── hls-code-standards.mdc    # Section 6, alwaysApply: true 
    │       └── hls-recording.mdc         # Section 7, alwaysApply: true
    ├── hls-core.mdc-template             # Core Rules Template
    ├── hls-code-standards.mdc-template   # Code Snapshot Standards Template
    ├── hls-recording.mdc-template        # Iteration Recording Rules Template
    ├── hls-env.conf                      # Environment configuration (hosts, IPs, DB, Vitis path)
    └── generate-mdc.sh                   # Script to generate .mdc rules from templates
```

### 2. Generate Cursor Rules (.mdc) on the Vitis-HLS Machine

Cursor rules are generated by merging three `.mdc-template` files and `hls-env.conf` in the `cursorwork/` directory, with output written to `cursorwork/.cursor/rules/`.

**Step 1: Verify `hls-env.conf` settings are correct**

```bash
cat ~/cursorwork/hls-env.conf
```

`hls-env.conf` full contents are shown below; modify according to your actual environment and save:

```bash
# ============================================================================
# HLS Lab Environment Configuration
# ============================================================================
# Purpose: Define the Knowledge Base host, network, tools, and FPGA targets
# Usage:   ./generate-mdc.sh reads this file to generate .cursor/rules/*.mdc
# Format:  KEY=VALUE (no quotes unless value contains spaces)
# Note:    Lines starting with # are comments
# ============================================================================

# --- Knowledge Base Host ---
KB_HOST_NAME=HLS01
KB_HOST_IP=192.168.1.11
KB_API_PORT=8000

# --- Database Connection ---
# (Default values; no changes needed if installation settings are unmodified)
DB_USER=hls_user
DB_PASS=hls_user_passwd
DB_NAME=hls_hls_knowledge
DB_PORT=5432

# --- Vitis HLS Tool ---
VITIS_HLS_SETTING_PATH=/tools/Xilinx/Vitis_HLS/2023.2/settings64.sh
VITIS_HLS_CMD=vitis_hls

# --- Default FPGA Target ---
TARGET_PART=xc7z020clg400-1
DEFAULT_CLOCK_PERIOD_NS=10
```

**Step 2: Run the generation script**

```bash
cd ~/cursorwork/
chmod +x ./generate-mdc.sh
./generate-mdc.sh
```

The script reads `hls-env.conf`, replaces all `{{variables}}` in the three `.mdc-template` files with actual values, and outputs three `.mdc` files to `.cursor/rules/`:

```
╔══════════════════════════════════════════════════════════╗
║  generate-mdc.sh                                         ║
╚══════════════════════════════════════════════════════════╝

KB Host:     HLS01 (192.168.1.11)

--- Current Environment ---
Hostname:    HLS02
IP Address:  192.168.1.12
Vitis HLS:   ✓ Installed (/tools/Xilinx/Vitis_HLS/2023.2/bin/vitis_hls)
KB API:      http://192.168.1.11:8000

Output dir:  /home/cursor2hls/cursorwork/.cursor/rules

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Processing: hls-core.mdc-template
  → .cursor/rules/hls-core.mdc
  ✓ {{KB_HOST_NAME}} → HLS01 (8 occurrence(s))
  ✓ {{KB_HOST_IP}} → 192.168.1.11 (9 occurrence(s))
  ...
  ✓ Substitution complete (421 lines)
...
✓ All done! No remaining {{variables}}

Generated files:
  hls-core.mdc              468 lines  32K
  hls-code-standards.mdc    471 lines  24K
  hls-recording.mdc         678 lines  44K
```

> HLS03 also needs to log in and repeat Steps 1–2 to generate its own `.mdc` rule files.

### 3. Install Cursor (Windows)

Go to the [Cursor website](https://cursor.com/download), download the **Windows (x64) (System)** version, and run the installer to complete installation.

### 4. Connect to Vitis-HLS Machine (Cursor Remote SSH)

The following steps use HLS02 as an example to illustrate the developer setup process; repeat the same steps for HLS03.

In Cursor, install the **Remote - SSH** extension and add an SSH Host:

```
Host Vitis-HLS02-Server
    HostName hls-external-ip
    User cursor2hls
    Port 1200
```

After connecting, **open `~/cursorwork/` as the workspace in Cursor** (File → Open Folder → select `/home/cursor2hls/cursorwork`).

> Cursor's `.mdc` rules must be located in the `cursorwork/.cursor/rules/`, If you open `~/` (the home directory), Cursor will look for rules in `~/.cursor/rules/` and will not find the generated `.mdc` files.

To verify that the rules are active, type `What rules are you following?` or `Summarize your active Cursor rules` in the Cursor chat. All three rules are set to `alwaysApply: true`; all three should appear in the Cursor chat response when you ask about active rules.

### 5. Connect to Knowledge Base (DBeaver + SSH Tunnel)

Both administrators and developers can use DBeaver to connect to the Knowledge Base, making it easy to inspect iteration records, synthesis results, and rule application statistics written via Cursor automation.

**Step 1: Download and Install DBeaver (Windows)**

Go to [DBeaver Community](https://dbeaver.io), download the Community Edition Windows installer, and complete the installation with default settings.

**Step 2: Choose Connection Method Based on Your Network**

Select the appropriate method depending on where your Windows machine is currently connected:

**Case A: Not on the company's internal network and not connected via VPN (SSH tunnel required)**

When on an external network, Windows cannot reach HLS01 (`192.168.1.11`) directly. You need to use HLS02 as a jump host via its external port forwarding, creating an SSH tunnel to forward traffic to HLS01's PostgreSQL.

Run in Windows Command Prompt (cmd):

```cmd
ssh -L 5432:192.168.1.11:5432 cursor2hls@hls-external-ip -p 1200
```

Command breakdown:

- `-L 5432:192.168.1.11:5432` — maps `localhost:5432` on your Windows machine through the tunnel to HLS01's `192.168.1.11:5432`
- `cursor2hls@hls-external-ip -p 1200` — connects via HLS02's external port forwarding (port 1200) as the jump host

Keep this window open after entering the password; closing it disconnects the tunnel. In DBeaver, set **Host** to `localhost` and **Port** to `5432`.

**Case B: Already on the company's internal network or connected via VPN (direct connection)**

No SSH tunnel needed. In DBeaver, set **Host** directly to `192.168.1.11` and **Port** to `5432`.

**Step 3: Add Connection in DBeaver**

Open DBeaver, click "New Database Connection" (<kbd>Ctrl+Shift+N</kbd>), select **PostgreSQL**, and fill in the host and port according to your case above, along with the following:

- **Database:** `hls_knowledge`
- **Username:** `hls_user`
- **Password:** `hls_user_passwd`

> **Account note:** DBeaver connects with the `hls_user` account for viewing data only; write and modify privileges require the admin account (`admin`).

Click "Test Connection". On first connection, you will be prompted to download the PostgreSQL driver; click "Download" then "Finish".

---

## System Features

### Two-Track Query Strategy

Cursor AI automatically performs a two-track query before each design, in the following order:

**Track 1 (Priority)**: Calls `/api/design/similar` to understand the performance ceiling and best optimization technique combinations for same-type projects (including pragmas, approach descriptions, and cursor_reasoning), sorted by ii_achieved. Records `pragmas_used` for Track 2 deduplication, and records `iteration_id` for querying full code when needed.

```bash
curl "http://localhost:8000/api/design/similar?project_type=fir&limit=10"

# Query full code of the best iteration when needed (approach description not specific enough, or best II differs greatly from current)
curl "http://localhost:8000/api/design/{iteration_id}/code"
```

**Track 2**: First calls `/api/rules/categories` to retrieve the category list (shared by all subsequent steps, no need to call again), then follows this flow:

```bash
curl "http://localhost:8000/api/rules/categories"
```

**Step 0 (Optional): Application category first**

If application type `T` (e.g., `fir`, `systolic`) can be clearly inferred from `USER_SPEC`, user messages, or known `project_type`, and the `categories` list contains the same string, query application-scoped rules first and add to this round's candidates:

```bash
curl "http://localhost:8000/api/rules/effective?category=${T}&project_type=${T}&min_success_rate=0"
```

If `categories` does not contain `T` or `T` cannot be reasonably inferred, skip Step 0. Regardless of Step 0, Path A or Path B must still be followed to fill in technical-category rules; application and technical rules are merged as candidates and do not override each other.

**Path A — Track 1 has similar projects**: Infer the most relevant technical categories from Track 1's `approach_description`, `pragmas_used`, `cursor_reasoning` (can be > 1), merged with any Step 0 application-scoped rules. First filter by `rule_text` semantic; if no semantic match, fall back to statistical filtering (`success_count > 0` → sort by `times_applied DESC`; `success_count = 0` → sort by `priority DESC`). Pragmas already seen in Track 1 are marked as "known effective" and not re-recommended.

```bash
curl "http://localhost:8000/api/rules/effective?category={inferred_category}&min_success_rate=0"
```

**Path B — Track 1 has no similar projects (starting from scratch)**: Cursor infers primary and candidate categories based on problem characteristics. Queries in order with fallback — stops when the previous step yields semantically matching results. Step 0 application-scoped rules and technical rules are merged and do not override each other:

- **Step 2-1: Primary Category** — semantic filter; if no match → statistical fallback (`success_count > 0` → `times_applied DESC`; `= 0` → `priority DESC`, prefer priority=9)
- **Step 2-2: Candidate Category (triggered when 2-1 yields no results at all)** — same as above
- **Step 2-3: No Category Filter × priority=9 (triggered when both 2-1 and 2-2 are empty)** — retrieve fundamental HLS principle rules (priority=9, applicable to any design)

```bash
# Steps 2-1 / 2-2
curl "http://localhost:8000/api/rules/effective?category={category}&min_success_rate=0"
# Step 2-3
curl "http://localhost:8000/api/rules/effective?min_success_rate=0"
# Cursor filter: priority = 9
```

> **API Parameter Note**: `/api/rules/effective` only supports four parameters: `project_type`, `category`, `rule_type`, `min_success_rate`. Filtering and sorting by `times_applied`, `success_count`, `priority`, as well as `rule_text` semantic matching, are all handled by Cursor after receiving the response.

#### Rule Priority

During rule import, priority is automatically set based on keywords in the rule text:

| Priority | Trigger Keywords                         | Semantics                   |
| -------- | ---------------------------------------- | --------------------------- |
| 9        | `always`, `must`, `critical`, `never`    | Mandatory, must not violate |
| 7        | `do not`, `avoid`, `ensure`, `should`    | Strongly recommended        |
| 5        | `consider`, `may`, `recommend`, `prefer` | Suggested, optional         |
| 4        | (no matching keyword)                    | Default value, general rule |

After combining results from both tracks, Cursor AI proposes optimization approaches and precisely references rule codes (R### / P###) in the design. At `complete_iteration`stage, the applied rules are also automatically written back to `rules_effectiveness` to update success rate statistics.

#### Rule Classification

Both rule files use `# Category: <name>` annotations to mark categories; `import_rules.py` reads this value directly and writes it to the database. Categories are entirely determined by manual annotation.

```
# Category: dataflow        ← rules below belong to this category
- [R001] Always use #pragma HLS DATAFLOW ...
- [R002] Ensure producers and consumers ...
```

Both `rules_ug1399.txt` and `rules_user_defined.txt` can freely add new categories. `import_rules.py` supports them without modification.

#### Manual Category Annotations

`rules_user_defined.txt` is the user-defined rules file. It can include technology-oriented categories such as `pipeline` and `memory`, as well as application-specific categories such as `fir`, `systolic`, and `cordic`. Examples from actual classifications:

| Category   | Description                         | Example Rules                                                                                        |
| ---------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `pipeline` | Pipeline and II optimization        | P011 `PIPELINE II=1 rewind`; P018 scalar accumulation in innermost loop prohibited                   |
| `memory`   | Array access and partitioning       | P033 off-chip access inside hot loop prohibited; P037 partition arrays per unrolled lane             |
| `fir`      | FIR filter application optimization | P068 merge shift and compute loops to eliminate dependencies; P069 add `rewind` for seamless overlap |
| `systolic` | Systolic array architecture         | P083 use next-state arrays to eliminate RAW hazards; P086 input temporal skew to align PE data       |

Technology-oriented categories such as `pipeline` and `memory` appear in both `rules_ug1399.txt` and `rules_user_defined.txt`. Application-specific categories such as `fir` and `systolic` exist only in `rules_user_defined.txt`. The API merges results from both sources automatically regardless of `official` / `user_defined`.

In Track 2 Step 0, Cursor infers the relevant categories from user input and calls `/api/rules/effective?category=<n>` to retrieve precisely matched rules:

```
User input: "FIR filter, target II=1"
  → Cursor infers categories: fir, pipeline
  → GET /api/rules/effective?category=fir      ← P068–P070 loop merge / rewind techniques
  → GET /api/rules/effective?category=pipeline ← R035–R037 + P011–P024 pipeline rules
  → Retrieves on-topic rules; skips unrelated categories such as systolic / interface
```

> **Naming convention**: Use generic technical names for technology-oriented categories (`pipeline`, `memory`); use application names for application-specific categories (`fir`, `systolic`, `cordic`). `project_type` tracks *what the project is*; `category` tracks *which optimization a rule belongs to* — the two are distinct.

Query rules:

```bash
# Unified query (recommended): filter by category + effectiveness, regardless of official / user_defined
curl "http://localhost:8000/api/rules/effective?category=pipeline&min_success_rate=0"

# All rules for a specific project_type (Cursor-side: first filter by rule_text semantic, then sort by success_count / times_applied / priority)
curl "http://localhost:8000/api/rules/effective?project_type=fir"

# Browsing purpose: filter by rule_type (not required in workflow)
curl "http://localhost:8000/api/rules/effective?rule_type=official&min_success_rate=0"
curl "http://localhost:8000/api/rules/effective?rule_type=user_defined&min_success_rate=0"
```

> **`project_type` filter behavior**: Statistics are scoped to the specified `project_type`. Rules never applied to that type still appear in results with `times_applied=0` — they are not excluded.

### Design Iteration Recording & Automation

Before each HLS task, Cursor Agent automatically verifies the current environment to confirm the HLS machine environment and API connection, ensuring correct API call routing. After synthesis, the Step 9 `complete_iteration` API completes iteration recording, synthesis result writing, and `rules_effectiveness` update in a single call, and writes `_rollback_info` snapshot (for precise rollback) and `_rules_applied` snapshot (structured record of applied rules) into `reference_metadata`; Step 10's local Markdown backup ensures design records are not lost even if the API is unavailable.

**Trigger condition**: `csim` (functional verification) **and** `csynth` (high-level synthesis) **both succeed**, then Cursor AI automatically executes the second half of the workflow (Steps 7–10). If either fails, the iteration is not recorded:

> ❗ **Header comment write timing**: When Cursor writes code, the .cpp file **does not contain** a file header comment — only the code body and three-line pragma comments above each `#pragma HLS`. After csim + csynth both succeed, the report is parsed for measured data, then the complete header comment is inserted at the top of .cpp (before all `#include`), and only then is code_snapshot assembled for writing to KB. All values in the header (Synthesis Result, Resources, each Optimization's Result) are measured values.

| Step    | Action                                                                                                                                                               |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Step 1  | Front-Capture: scan user messages, maintain USER_REF_CODE / USER_SPEC                                                                                                |
| Step 2  | Two-track query: use `/api/design/similar` for similar designs (Track 1); use `/api/rules/effective` for rules (Track 2)                                             |
| Step 3  | Bind Rules: bind selected rules to APPLIED_RULES; record reasoning in `cursor_reasoning`                                                                             |
| Step 4  | Propose optimization approach (based on KB knowledge and user input)                                                                                                 |
| Step 5  | Write code + pragma comments (three-line comment above each `#pragma HLS`; **do not write file header comment at this stage**)                                       |
| Step 6  | Run csim + csynth (if either fails → stop, do not record)                                                                                                            |
| Step 7  | Parse csynth report (II, Latency, Resources, Timing); insert complete header comment in one pass (measured values)                                                   |
| Step 8  | Use `/api/projects` + `project_name` exact match to retrieve `project_id` (**critical** — avoids duplicate project creation)                                         |
| Step 9  | Call `POST /api/design/complete_iteration`                                                                                                                           |
| Step 10 | Create / update local markdown document backup                                                                 |
| Step 11 | If II target not met, update `previous_ii` baseline from this result, select next-best pragma combination not yet tried, and return to Step 2 for the next iteration |

> **Step 7 Applied Rules recording rule**: All rules that Cursor referenced or applied when reasoning about optimization direction, regardless of whether rule_code can be confirmed, must be recorded in the `code_snapshot` header's Applied Rules section. When rule_code is known, write `P###/R###: rule_text`; when rule_code cannot be confirmed, write only rule_text — omission is not allowed.

### Reproduce Specific Iteration

When you need to verify historical iteration results, or use a historical iteration as the starting point for new optimization, follow these steps to reproduce. Reproduction is for verification or learning only and does not trigger the automatic recording process (code_snapshot is identical to the original record, recording would produce duplicate data).

**Step 1: Retrieve target iteration_id and project_id**

```bash
# A. User specifies project and iteration number
curl "http://localhost:8000/api/analytics/project/${PROJECT_ID}/progress"
# B. Query from best designs by project_type
curl "http://localhost:8000/api/design/similar?project_type=fir&limit=10"
# Both return iteration_id and project_id
```

**Step 2: Retrieve complete code_snapshot and restore files**

```bash
curl "http://localhost:8000/api/design/${ITER_ID}/code"
# Returns: code_snapshot, approach_description, code_hash, pragmas_used,
#          user_specification, cursor_reasoning, prompt_used, user_reference_code
```

Split code_snapshot by separator lines (`// === {filename} ===`) to restore actual files. File order in code_snapshot is [.h] → .cpp → testbench → [.inc]. `.inc` files restored from code_snapshot are placed in the same directory as `.cpp` (they are referenced via `#include "*.inc"` and do not need `add_files` in run_hls.tcl).

**Step 3: Retrieve environment parameters and generate run_hls.tcl**

code_snapshot does not include `run_hls.tcl`; it needs to be generated automatically from the restored file information:

- **top function**: Inferred from the function signature in code_snapshot (e.g., `void fir(...)` → `set_top fir`)
- **add_files**: extract all filenames from separator lines, skip `*_tb.cpp` and `*.inc`, then add in order: `.h` (if present) → `.cpp`
- **testbench**: `*_tb.cpp` filename from separator lines, added via `add_files -tb`
- **`.inc` files**: Not added via `add_files`; they are `#include`d by `.cpp` and only need to be in the same directory
- **target_device**: Use the `TARGET_PART` value from `hls-env.conf` (already substituted into the rules by `generate-mdc.sh`)
- **clock_period**: Use the `DEFAULT_CLOCK_PERIOD_NS` value from `hls-env.conf` (already substituted into the rules by `generate-mdc.sh`)

**Step 4: Re-run synthesis and verify**

```bash
source /path/to/settings64.sh
vitis_hls -f run_hls.tcl   # Run csim_design + csynth_design
```

After reproduction, compare II, Latency, Resources against the original record. code_snapshot header comments contain complete measured data (Synthesis Result, Resources), which can be compared directly from the header without additional KB `synthesis_results` queries. If reproduction results differ from the original record, possible causes include different Vitis HLS versions or different FPGA targets.

### Knowledge Base Access Policy (Multi-User)

The Knowledge Base is shared by all Cursor HLS Users. The success rate statistics in `rules_effectiveness` affect rule recommendations for every developer, so the following access policies apply:

| Operation Type                        | Performer                           | Description                                                                |
| ------------------------------------- | ----------------------------------- | -------------------------------------------------------------------------- |
| Query rules / designs                 | Cursor HLS User                     | Can query anytime; does not affect shared data                             |
| Write new iteration                   | Cursor HLS User                     | Only via `complete_iteration` automatic completion                         |
| Update rule statistics                | `complete_iteration` auto-execution | Updated internally by the API within a transaction; no standalone endpoint |
| Rollback (remove project / iteration) | System Administrator                | System administration privileges required                                  |
| KB backup / restore / reset           | System Administrator                | System administration privileges required                                  |

**Concurrent Write Safety**: When multiple developers use the Knowledge Base simultaneously, the API has built-in collision prevention. If a project with the same name already exists, the API returns **409 Conflict** with `existing_project_id`; Cursor retries `complete_iteration` with that ID, with no developer coordination needed.

### API Endpoint Reference

Cursor AI automatically calls the appropriate endpoints based on the design phase — before design, uses `/api/design/similar` to query similar design cases (learning best optimization methods), `/api/rules/categories` to retrieve the category list, and `/api/rules/effective` to retrieve rules (Cursor-side first filters by `rule_text` semantic for on-topic rules, then sorts by success_count / times_applied / priority); after synthesis, retrieves `project_id` via Automatic Design Iteration Recording first, then uses `/api/design/complete_iteration` to complete all data writing in one call (`iteration_number` is automatically computed by the API); to view project iterations, calls `/api/analytics/.../progress`. The entire process is automatically orchestrated by Cursor Agent; developers do not need to manually execute any API calls.

| Endpoint                                       | Method | Description                                                                                                                                      |
| ---------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/health`                                      | GET    | Health check                                                                                                                                     |
| `/api/projects`                                | GET    | List all projects (supports type, limit, offset)                                                                                                 |
| `/api/projects`                                | POST   | Create new project (Concurrent Write Safety)                                                                                                     |
| `/api/projects/{project_id}`                   | GET    | Get single project details                                                                                                                       |
| `/api/design/similar`                          | GET    | Query similar designs (for learning; includes cursor_reasoning; excludes code_snapshot / prompt_used / user_reference_code / reference_metadata) |
| `/api/design/{iteration_id}/code`              | GET    | Get full details of a specific iteration (code_snapshot, cursor_reasoning, prompt_used, user_reference_code; **excludes reference_metadata**)    |
| `/api/rules/effective`                         | GET    | Query rules (supports rule_type filter, default min_success_rate=0.0)                                                                            |
| `/api/rules/categories`                        | GET    | Return all category list (for two-track query category inference)                                                                                |
| `/api/design/complete_iteration`               | POST   | Record a complete iteration                                                                                                                      |
| `/api/analytics/project/{project_id}/progress` | GET    | Return all iteration results for a project                                                                                                       |
| `/docs`                                        | GET    | Swagger UI interactive documentation                                                                                                             |

> Before recording an iteration, retrieve `project_id` via Design Iteration Recording & Automation **Post-Synthesis** — never from `/api/design/similar` results, which are sorted by performance and may be owned by another project.

> `rules_effectiveness` updates are only performed automatically by `complete_iteration` within a transaction.

**For detailed request/response formats, complete operation examples, and end-to-end workflows, see the Detailed API Examples & Operations Guide**.

## Troubleshooting

**DBeaver cannot connect to the database**

Symptom: DBeaver shows connection timeout or connection refused. Common causes and troubleshooting order:

1. **SSH tunnel dropped**: Tunnels disconnect automatically after prolonged inactivity or network changes. Re-establish the tunnel in Windows CMD:
   
   ```bash
   ssh -L 5432:192.168.1.11:5432 cursor2hls@hls-external-ip -p 1200
   ```

2. **PostgreSQL service not running**: SSH into the Knowledge Base host and run `docker ps` to confirm the PostgreSQL container status is `Up`; if not running, execute `docker compose up -d` in `~/hls-kb/`

**Cursor reports insufficient permissions or cannot execute commands**

Symptom: Cursor shows "permission denied" or commands produce no response. Common causes:

1. **Cursor is in Ask mode**: In Ask mode, Cursor can only answer questions and cannot execute terminal commands. Switch to Agent mode in the Cursor interface before running HLS tasks
2. **SSH connection dropped**: Cursor Remote SSH may disconnect after prolonged inactivity. Re-open the Cursor Remote SSH connection to the target Vitis-HLS host

---

**Version**: v1.0  
**Last Updated**: 2026-03-28

---

## Acknowledgements

We would like to express our sincere gratitude to the following individuals and organizations:

**Prof. Jiin Lai** and the Research Team  
National Tsing Hua University  
For their invaluable guidance on HLS design methodology and research topics.

**Eric Chang** and the AMD Xilinx Team  
For their professional advice and resource support on Vitis HLS technology.
