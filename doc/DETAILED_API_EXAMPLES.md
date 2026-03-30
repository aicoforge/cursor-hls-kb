# HLS Knowledge Base — Detailed API Examples & Operations Guide

[![License CC BYNC 40](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![For Education](https://img.shields.io/badge/Use-Education%20%26%20Academic-green.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

> Copyright (c) 2026 AICOFORGE. All rights reserved.
> CC BY-NC 4.0 — non-commercial use only. See LICENSE.
> Commercial use: kevinjan@aicoforge.com

---

## 1. API Response Format Reference

### 1.1 GET /health

**Purpose**: Confirm API service and database connection status.

**Request**:

```bash
curl -s "http://localhost:8000/health" | python3 -m json.tool
```

**Response (normal)**:

```json
{
    "status": "healthy",
    "database": "connected",
    "timestamp": "2026-03-12T14:51:41.407136"
}
```

**Response (abnormal)**:

```json
{
    "status": "unhealthy",
    "error": "connection refused",
    "timestamp": "2026-03-12T14:51:41.407136"
}
```

**Field description**:

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | `"healthy"` or `"unhealthy"` |
| `database` | string | Only present when healthy, value is `"connected"` |
| `error` | string | Only present when unhealthy, contains error message |
| `timestamp` | string | ISO 8601 UTC timestamp |

---

### 1.2 GET /api/projects

**Purpose**: List all projects (REST convention: GET = list). Can query the projects table directly without going through design/similar.

**Parameters**:

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `type` | string | No  | null | Filter project type (`fir`, `matmul`, `conv`, etc.) |
| `limit` | int | No  | 50  | Maximum number of records (1–200) |
| `offset` | int | No  | 0   | Pagination offset |

**Request**:

```bash
# List all projects
curl -s "http://localhost:8000/api/projects" | python3 -m json.tool

# Filter by fir type
curl -s "http://localhost:8000/api/projects?type=fir&limit=20" | python3 -m json.tool
```

**Response**:

```json
{
    "total": 16,
    "limit": 50,
    "offset": 0,
    "results": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "name": "FIR128_Demo",
            "type": "fir",
            "description": "128-tap FIR filter optimization journey",
            "target_device": "xc7z020clg484-1",
            "created_at": "2025-11-03T11:15:07.059396",
            "updated_at": "2025-11-03T11:15:07.059396"
        }
    ]
}
```

**Response field description**:

| Field | Type | Description |
| --- | --- | --- |
| `total` | int | Total number of matching records |
| `limit` | int | Limit used in this query |
| `offset` | int | Offset used in this query |
| `results` | array | Project list; each entry contains id, name, type, description, target_device, created_at, updated_at |

---

### 1.3 POST /api/projects

**Purpose**: Create a new project (REST convention: POST = create). Typically auto-created internally by `complete_iteration`, but can also be called in advance.

**Concurrent safety**: Uses `INSERT ON CONFLICT` atomic operation. When multiple users simultaneously create projects with the same name and type, only one succeeds; others receive 409 + `existing_project_id`.

**Request Body (JSON)**:

```json
{
    "name": "MyFIR_Project",
    "type": "fir",
    "description": "128-tap FIR optimization",
    "target_device": "xc7z020clg484-1"
}
```

**Request field description**:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Project name |
| `type` | string | Yes | Project type (`fir`, `matmul`, `conv`, etc.) |
| `description` | string | No  | Project description |
| `target_device` | string | No  | Target device (default `xilinx_fpga_board_b`) |

**Successful response**:

```json
{
    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "MyFIR_Project",
    "type": "fir"
}
```

---

### 1.4 GET /api/design/similar

**Purpose**: Query design iterations for same-type projects, sorted by `ii_achieved` ascending (best first).

**Parameters**:

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `project_type` | string | Yes | —   | Project type (`fir`, `matmul`, `conv`, etc.) |
| `target_ii` | int | No  | null | Filter: only return results where `ii_achieved <= target_ii` |
| `limit` | int | No  | 5   | Number of results (1–20) |

#### Example 1: Query all FIR designs (without target_ii)

**Request**:

```bash
curl -s "http://localhost:8000/api/design/similar?project_type=fir&limit=5" | python3 -m json.tool
```

**Response**:

```json
{
    "query": {
        "project_type": "fir",
        "target_ii": null,
        "limit": 5
    },
    "results": [
        {
            "iteration_id": "0d769cd5-fdf9-4bd5-aa4b-b620431d59c8",
            "project_id": "550e8400-e29b-41d4-a716-446655440001",
            "project_name": "FIR128_Demo",
            "project_type": "fir",
            "iteration_number": 5,
            "approach_description": "Streaming AXIS + ap_ctrl_none + STREAM depth=8 + ARRAY_PARTITION complete + full UNROLL + PIPELINE II=1",
            "code_hash": "b9c7ecc4cbb4f06cf365b577b81bdb36d9722a18be7c92ab42d0af752c9b1a77",
            "pragmas_used": [
                "#pragma HLS INTERFACE axis port=s_in",
                "#pragma HLS INTERFACE axis port=s_out",
                "#pragma HLS INTERFACE ap_ctrl_none port=return",
                "#pragma HLS STREAM variable=s_in depth=8",
                "#pragma HLS STREAM variable=s_out depth=8",
                "#pragma HLS ARRAY_PARTITION variable=shift_reg complete dim=1",
                "#pragma HLS ARRAY_PARTITION variable=coeffs complete dim=1",
                "#pragma HLS PIPELINE II=1",
                "#pragma HLS UNROLL (on shift + MAC loops)"
            ],
            "user_specification": null,
            "cursor_reasoning": null,
            "ii_achieved": 1,
            "ii_target": 1,
            "latency_cycles": 9,
            "resource_usage": "{\"FF\": 4772, \"DSP\": 2, \"LUT\": 2306, \"BRAM_18K\": 0}",
            "created_at": "2025-11-04T14:37:12.043838"
        },
        {
            "iteration_id": "6fa68a42-9ce5-4af5-92ac-90a61bb8b78c",
            "project_id": "bb9d653b-8fee-43d9-8a9a-a80c43ced4fd",
            "project_name": "FIR128_Cursor_Optimized",
            "project_type": "fir",
            "iteration_number": 1,
            "approach_description": "Streaming AXIS + ap_ctrl_none + STREAM depth=8 + complete partition + full unroll on merged shift+MAC loop; PIPELINE II=1 on SampleLoop",
            "code_hash": "539d769aebf059bad21094e2cd97bacada339f6600d054d1dc6484f66d261566",
            "pragmas_used": [
                "#pragma HLS INTERFACE axis port=s_in",
                "#pragma HLS INTERFACE axis port=s_out",
                "#pragma HLS INTERFACE ap_ctrl_none port=return",
                "#pragma HLS STREAM variable=s_in depth=8",
                "#pragma HLS STREAM variable=s_out depth=8",
                "#pragma HLS ARRAY_PARTITION variable=delay_line complete dim=1",
                "#pragma HLS ARRAY_PARTITION variable=fir_coeffs complete dim=1",
                "#pragma HLS PIPELINE II=1 (on SampleLoop)",
                "#pragma HLS UNROLL (on ShiftAndMac loop)"
            ],
            "user_specification": "128-tap FIR, 16-bit samples, AXIS streaming, target II=1, <=2 DSPs",
            "cursor_reasoning": "Applied complete array partition on both delay_line and coefficients to enable full parallel access, merged shift and MAC into single loop to reduce overhead, used PIPELINE II=1 on outer sample loop",
            "ii_achieved": 1,
            "ii_target": 1,
            "latency_cycles": 9,
            "resource_usage": "{\"FF\": 5497, \"DSP\": 2, \"LUT\": 3532, \"BRAM_18K\": 0}",
            "created_at": "2025-12-02T17:07:29.313044"
        }
    ]
}
```

**Response field description (per result)**:

| Field | Type | Description |
| --- | --- | --- |
| `iteration_id` | UUID | Iteration unique identifier (use to query full details including code_snapshot) |
| `project_id` | UUID | Indicates which project this iteration belongs to; **not for recording purposes** (when recording, `project_id` must be obtained by exact name match via `GET /api/projects`) |
| `project_name` | string | Project name |
| `project_type` | string | Project type |
| `iteration_number` | int | Iteration sequence number (1, 2, 3...) |
| `approach_description` | string | Optimization approach description |
| `code_hash` | string | SHA256 (full text hash of code_snapshot, for deduplication, 64 hex chars) |
| `pragmas_used` | string[] | List of pragmas used |
| `user_specification` | string\\|null | User's requirements and constraints |
| `cursor_reasoning` | string\\|null | Cursor's optimization reasoning (why this approach was chosen) |
| `ii_achieved` | int | Actual II achieved |
| `ii_target` | int | Target II value |
| `latency_cycles` | int\\|null | Latency in cycles (may be null) |
| `resource_usage` | string | Resource usage in JSON string format |
| `created_at` | string | Creation time (ISO 8601) |

> **Warning**: `resource_usage` in the response is a **JSON string** (not an object); you need an additional `json.loads()` or `jq` parse when using it.

> **Warning**: `code_snapshot`, `prompt_used`, `user_reference_code`, `reference_metadata` **are not returned by this endpoint** — this is by design. For full code and reasoning details, use `GET /api/design/{iteration_id}/code`.

#### Example 2: With target_ii filter

```bash
curl -s "http://localhost:8000/api/design/similar?project_type=fir&target_ii=128&limit=3" | python3 -m json.tool
```

This query only returns results where `ii_achieved <= 128`, sorted by `ii_achieved` ascending.

#### Example 3: Query non-existent type

```bash
curl -s "http://localhost:8000/api/design/similar?project_type=nonexist&limit=1" | python3 -m json.tool
```

**Response**:

```json
{
    "query": {
        "project_type": "nonexist",
        "target_ii": null,
        "limit": 1
    },
    "results": []
}
```

> Empty results do not return 404; instead, a normal 200 OK with an empty `results` array is returned.

---

### 1.5 GET /api/design/{iteration_id}/code

**Purpose**: Retrieve full details of a specific iteration (including `code_snapshot`, reasoning, reference code, and all design context).

**Path parameter**:

| Parameter | Type | Description |
| --- | --- | --- |
| `iteration_id` | UUID | Retrieved from the `/api/design/similar` response |

**Request**:

```bash
# First retrieve iteration_id from the similar endpoint
ITER_ID=$(curl -s "http://localhost:8000/api/design/similar?project_type=fir&limit=1" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['results'][0]['iteration_id'])")

# Then query full code
curl -s "http://localhost:8000/api/design/${ITER_ID}/code" | python3 -m json.tool
```

**Response**:

```json
{
    "iteration_id": "0d769cd5-fdf9-4bd5-aa4b-b620431d59c8",
    "iteration_number": 5,
    "project_name": "FIR128_Demo",
    "approach_description": "Streaming AXIS + ap_ctrl_none + ...",
    "code_snapshot": "// ============================================================================\n// FIR128_Demo - Iteration #5: ...\n// ...\nvoid FIR(hls::stream<data_t> &s_in, hls::stream<data_t> &s_out) {\n    ...\n}\n",
    "code_hash": "b9c7ecc4cbb4f06cf365b577b81bdb36d9722a18be7c92ab42d0af752c9b1a77",
    "pragmas_used": [
        "#pragma HLS INTERFACE axis port=s_in",
        "#pragma HLS ARRAY_PARTITION variable=shift_reg complete dim=1",
        "#pragma HLS PIPELINE II=1",
        "#pragma HLS UNROLL"
    ],
    "user_specification": "128-tap FIR, target II=1, <=2 DSPs",
    "cursor_reasoning": "Applied complete array partition on both delay_line and coefficients to enable full parallel access, merged shift and MAC into single loop",
    "prompt_used": "Optimize this 128-tap FIR filter to achieve II=1 with minimal DSP usage...",
    "user_reference_code": "// Original unoptimized FIR\nvoid fir(int input, int *output) {\n    static int shift_reg[128];\n    ...\n}"
}
```

**Response field description**:

| Field | Type | Description |
| --- | --- | --- |
| `iteration_id` | UUID | Iteration ID |
| `iteration_number` | int | Iteration sequence number |
| `project_name` | string | Project name |
| `approach_description` | string | Optimization approach description |
| `code_snapshot` | string | **Complete HLS code** (with comments) |
| `code_hash` | string | SHA256 (full text hash of code_snapshot) |
| `pragmas_used` | string[] | List of pragmas used |
| `user_specification` | string\\|null | User's requirements and constraints |
| `cursor_reasoning` | string\\|null | Cursor's optimization reasoning |
| `prompt_used` | string\\|null | Cursor prompt that generated this iteration |
| `user_reference_code` | string\\|null | User-provided reference code (original/unoptimized version) |

> **Warning**: `reference_metadata` **is not returned by this endpoint** (contains administrator-only `_rollback_info` and `_rules_applied`; Cursor developers do not need to read it).

**Extract pure code to file**:

```bash
curl -s "http://localhost:8000/api/design/${ITER_ID}/code" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['code_snapshot'])" \
  > reference_code.cpp
```

---

### 1.6 GET /api/rules/effective

**Purpose**: Query rules and their application effectiveness statistics.

**Parameters**:

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `project_type` | string | No  | null | Filter by project type (`fir`, `matmul`, etc.) |
| `category` | string | No  | null | Filter by rule category (`pipeline`, `dataflow`, `memory`, etc.) |
| `rule_type` | string | No  | null | Filter by rule type: **only supports `official` or `user_defined`** |
| `min_success_rate` | float | No  | 0.0 | Minimum success rate filter (0.0–1.0); `success_rate = success_count / times_applied`; when `times_applied=0`, `success_rate=0` |

#### Example 1: Query all official rules (including never-applied ones)

```bash
curl -s "http://localhost:8000/api/rules/effective?rule_type=official&min_success_rate=0&project_type=fir" \
  | python3 -m json.tool
```

**Response**:

```json
{
    "filters": {
        "project_type": "fir",
        "category": null,
        "rule_type": "official",
        "min_success_rate": 0.0
    },
    "rules": [
        {
            "id": "0cfb8be6-665d-5382-88fd-864795184931",
            "rule_code": "R063",
            "rule_type": "official",
            "rule_text": "Accept II > 1 only as a deliberate trade-off (e.g. saving area); otherwise always strive for II=1.",
            "category": "pipeline",
            "priority": 9,
            "source": "UG1399",
            "times_applied": 1,
            "success_count": 1,
            "success_rate": 1.0,
            "avg_ii_improvement": 127.0
        },
        {
            "id": "fe776e1a-3d28-54f5-8bf7-b2e187dc5758",
            "rule_code": "R284",
            "rule_type": "official",
            "rule_text": "Each module must read exactly one control token per data unit (or per defined protocol).",
            "category": "interface",
            "priority": 9,
            "source": "UG1399",
            "times_applied": 0,
            "success_count": 0,
            "success_rate": 0.0,
            "avg_ii_improvement": null
        }
    ]
}
```

**Response field description (per rule)**:

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Rule unique identifier |
| `rule_code` | string | Rule code (`R001`–`R287` official / `P001`–`P999` user-defined) |
| `rule_type` | string | `"official"` or `"user_defined"` |
| `rule_text` | string | Full rule text description |
| `category` | string | Rule category (`pipeline`, `dataflow`, `memory`, `interface`, `optimization`, `systolic`, etc.) |
| `priority` | int | Priority (1–10, 9 is highest) |
| `source` | string | Source (`"UG1399"` official / `"User"` user-defined) |
| `times_applied` | int | Cumulative application count |
| `success_count` | int | II improvement success count (incremented when both `rule_app.success=true` and `previous_ii - current_ii > 0`) |
| `success_rate` | float | Success rate (0.0–1.0; **note**: theoretical maximum is 1.0, but may exceed 1.0 with data anomalies) |
| `avg_ii_improvement` | float\\|null | Average II improvement (cycles); null if never applied |

> **Warning**: Default `min_success_rate=0.0` means results **include never-applied rules** (`times_applied=0`, `success_rate=0.0`). Cursor should sort by `success_rate DESC` on its own, prioritizing high success rate rules. If too many results, gradually increase: `min_success_rate=0.3` → `0.5` → `0.7`.

> **Warning — project_type filter behavior**: When querying with `project_type`, the returned `times_applied` / `success_count` / `success_rate` / `avg_ii_improvement` only reflect statistics for **that project_type**. Rules with application records for other project_types but none for the target project_type still appear (`times_applied=0`) and are not excluded. Without `project_type`, cross-project_type aggregate statistics are returned.

#### Example 2: Query user-defined rules

```bash
curl -s "http://localhost:8000/api/rules/effective?rule_type=user_defined&min_success_rate=0" \
  | python3 -m json.tool
```

**Response excerpt**:

```json
{
    "filters": {
        "project_type": null,
        "category": null,
        "rule_type": "user_defined",
        "min_success_rate": 0.0
    },
    "rules": [
        {
            "id": "484aa929-328c-5549-8a12-72e690ee20c9",
            "rule_code": "P001",
            "rule_type": "user_defined",
            "rule_text": "Always aim for II=1 and full DATAFLOW pipeline.",
            "category": "optimization",
            "priority": 9,
            "source": "User",
            "times_applied": 1,
            "success_count": 1,
            "success_rate": 1.0,
            "avg_ii_improvement": 130.0
        },
        {
            "id": "9e63cab0-7a55-58fa-928a-667d5522785d",
            "rule_code": "P002",
            "rule_type": "user_defined",
            "rule_text": "Use pure DATAFLOW structure.",
            "category": "optimization",
            "priority": 4,
            "source": "User",
            "times_applied": 1,
            "success_count": 1,
            "success_rate": 1.0,
            "avg_ii_improvement": 6.0
        }
    ]
}
```

#### Example 3: Query high success rate rules (mixed official + user_defined)

```bash
curl -s "http://localhost:8000/api/rules/effective?min_success_rate=0.7&project_type=fir" \
  | python3 -m json.tool
```

When `rule_type` is not specified, both official rules and user-defined rules are returned, sorted by `success_rate DESC, priority DESC`.

#### Example 4: No filter (view all rules)

```bash
curl -s "http://localhost:8000/api/rules/effective?min_success_rate=0" | python3 -m json.tool
```

> **Note**: Without `project_type`, rule effectiveness statistics for **all project types** are returned (including NULL project_type). The number of rules may be large (287 official + 100+ user-defined).

---

### 1.6a GET /api/rules/categories

**Purpose**: Return all category values present in `hls_rules` (alphabetically sorted). Used by Cursor during the two-track query category inference phase, selecting from a known set rather than free inference.

**Parameters**: None

**Request**:

```bash
curl -s "http://localhost:8000/api/rules/categories" | python3 -m json.tool
```

**Response**:

```json
{
    "categories": [
        "code",
        "cordic",
        "data_types",
        "dataflow",
        "fir",
        "hierarchical",
        "interface",
        "memory",
        "optimization",
        "pipeline",
        "structural",
        "synthesis",
        "systolic"
    ]
}
```

**Field description**:

| Field | Type | Description |
| --- | --- | --- |
| `categories` | string[] | All existing category values, alphabetically sorted. Content changes as `hls_rules` table data changes |

> **When to use**: In the two-track query Path A Step 1 and Path B Step 1 (Section 5), call this endpoint first to get the list, then select the most relevant category.

---

### 1.7 POST /api/design/complete_iteration

**Purpose**: Complete a full iteration record in a single API call (create project + record iteration + synthesis result + rule effectiveness update + write rollback information).

**Request Body (JSON)**:

```json
{
    "project_id": "550e8400-e29b-41d4-a716-446655440001",
    "project_name": "FIR128_Demo",
    "project_type": "fir",
    "target_device": "xc7z020clg400-1",
    "iteration": {
        "project_id": "550e8400-e29b-41d4-a716-446655440001",
        "approach_description": "Array partition complete + full unroll + PIPELINE II=1",
        "code_snapshot": "// ============================================================================\n// FIR128 - Iteration #6: ...\nvoid FIR(...) { ... }\n",
        "pragmas_used": [
            "#pragma HLS ARRAY_PARTITION variable=shift_reg complete dim=1",
            "#pragma HLS PIPELINE II=1",
            "#pragma HLS UNROLL"
        ],
        "prompt_used": "User's original request text",
        "cursor_reasoning": "Reasoning for choosing this optimization approach",
        "user_reference_code": null,
        "user_specification": "Target II=1, DSP<=2",
        "reference_metadata": {"language": "cpp", "ii_top": 517, "ii_top_previous": 517}
    },
    "synthesis_result": {
        "ii_achieved": 1,
        "ii_target": 1,
        "latency_cycles": 9,
        "timing_met": true,
        "resource_usage": {"DSP": 2, "LUT": 2306, "FF": 4772, "BRAM_18K": 0},
        "clock_period_ns": 10.0
    },
    "rules_applied": [
        {
            "rule_code": "P001",
            "rule_description": "Always aim for II=1",
            "previous_ii": 128,
            "current_ii": 1,
            "success": true,
            "category": "optimization"
        },
        {
            "rule_code": "R063",
            "rule_description": "Always strive for II=1",
            "previous_ii": 128,
            "current_ii": 1,
            "success": true,
            "category": "pipeline"
        }
    ]
}
```

**Request field description**:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `project_id` | UUID | Yes | Retrieved from Step 0 query, or generate for new project with `python3 -c "import uuid; print(uuid.uuid4())"` |
| `project_name` | string | No  | Project name (recommended for new projects) |
| `project_type` | string | Yes | Project type (`fir`, `matmul`, `conv`, etc.) |
| `target_device` | string | No  | Target device (default `xilinx_fpga_board_a`; in normal workflow, filled in by Cursor with the actual FPGA part) |
| `iteration` | object | Yes | Iteration content (see table below) |
| `synthesis_result` | object | Yes | Synthesis result (see table below) |
| `rules_applied` | array | No  | List of applied rules (can be empty array `[]`) |

**iteration sub-fields**:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `project_id` | UUID | Yes | Must match the outer `project_id` |
| `approach_description` | string | Yes | Optimization approach description |
| `code_snapshot` | string | Yes | Complete HLS code (with comments) |
| `pragmas_used` | string[] | Yes | List of pragmas used |
| `prompt_used` | string | No  | User's original request |
| `cursor_reasoning` | string | No  | Cursor AI's reasoning process |
| `user_reference_code` | string | No  | User-provided reference code |
| `user_specification` | string | No  | User's requirements and constraints |
| `reference_metadata` | object | No  | Metadata (API automatically appends `_rollback_info` and `_rules_applied`) |

**synthesis_result sub-fields**:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ii_achieved` | int | Yes | Actual II achieved |
| `ii_target` | int | Yes | Target II |
| `latency_cycles` | int | Yes | Latency in cycles |
| `timing_met` | bool | Yes | Whether timing was met |
| `resource_usage` | object | Yes | Resource usage (`{"DSP":2, "LUT":348, "FF":447, "BRAM_18K":2}`) |
| `clock_period_ns` | float | No  | Clock period (default 10.0) |

**rules_applied sub-fields (per entry)**:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `rule_code` | string | No  | Preferred (e.g., `P001`, `R063`), 100% exact match; filled by Cursor after semantic matching |
| `rule_description` | string | No  | Rule description (for reference only, not used for matching) |
| `previous_ii` | int | Yes | `ii_bneck` baseline before this optimization: Layer 1 (has prior record) = last iteration's `ii_bneck`; Layer 2 (first iteration) = estimated `ii_bneck` baseline → see mdc 「previous_ii Baseline Definition」 |
| `current_ii` | int | Yes | `ii_bneck` from this iteration's csynth report (same value as `synthesis_result.ii_achieved`) |
| `success` | bool | Yes | `(current_ii < previous_ii)` — both values must be `ii_bneck`; do not use `ii_top` or latency |
| `category` | string | No  | Rule category |

**Successful response**:

```json
{
    "status": "success",
    "iteration_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "iteration_number": 6,
    "project_id": "550e8400-e29b-41d4-a716-446655440001",
    "rules_recorded": 2,
    "message": "Complete iteration record created (iteration #6, 2 rule effectiveness record(s) updated)"
}
```

**Response field description**:

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | `"success"` |
| `iteration_id` | UUID | Newly created iteration ID |
| `iteration_number` | int | Auto-incremented iteration sequence number |
| `project_id` | UUID | Project ID used |
| `rules_recorded` | int | Number of rules successfully matched and recorded |
| `message` | string | Human-readable result message |

> **Important**: `iteration_number` is automatically computed by the API (takes the current maximum sequence number for the project + 1). If the returned `iteration_number` is not the expected value (e.g., expected 6 but got 1), it means an incorrect `project_id` was used.

---

### 1.8 GET /api/analytics/project/{project_id}/progress

**Purpose**: Retrieve all iteration optimization progress for a specified project, including II improvement calculations between iterations.

**Path parameter**:

| Parameter | Type | Description |
| --- | --- | --- |
| `project_id` | UUID | Retrieved from the `/api/design/similar` response |

**Request**:

```bash
curl -s "http://localhost:8000/api/analytics/project/550e8400-e29b-41d4-a716-446655440001/progress" \
  | python3 -m json.tool
```

**Response**:

```json
{
    "project_id": "550e8400-e29b-41d4-a716-446655440001",
    "total_iterations": 5,
    "iterations": [
        {
            "iteration_id": "a1b2c3d4-0001-0001-0001-000000000001",
            "iteration_number": 1,
            "approach_description": "Baseline design with separate shift and MAC loops",
            "ii_achieved": 264,
            "latency_cycles": null,
            "timing_met": true,
            "resource_usage": "{\"DSP\": 1}",
            "created_at": "2025-10-27T19:15:07.060267"
        },
        {
            "iteration_id": "a1b2c3d4-0001-0001-0001-000000000002",
            "iteration_number": 2,
            "approach_description": "Merged shift and MAC into single loop using ternary operator",
            "ii_achieved": 134,
            "latency_cycles": null,
            "timing_met": true,
            "resource_usage": "{\"DSP\": 1}",
            "created_at": "2025-10-29T19:15:07.060267",
            "ii_improvement": 130
        },
        {
            "iteration_id": "a1b2c3d4-0001-0001-0001-000000000003",
            "iteration_number": 3,
            "approach_description": "Applied pipeline rewind optimization to merged loop",
            "ii_achieved": 128,
            "latency_cycles": null,
            "timing_met": true,
            "resource_usage": "{\"DSP\": 1}",
            "created_at": "2025-10-31T19:15:07.060267",
            "ii_improvement": 6
        },
        {
            "iteration_id": "a1b2c3d4-0001-0001-0001-000000000004",
            "iteration_number": 4,
            "approach_description": "Array partition (cyclic factor=2) + Partial unroll (factor=2) with merged MAC and shift loop",
            "ii_achieved": 128,
            "latency_cycles": 131,
            "timing_met": true,
            "resource_usage": "{\"FF\": 339, \"DSP\": 2, \"LUT\": 408, \"BRAM_18K\": 2}",
            "created_at": "2025-11-03T12:20:14.467801",
            "ii_improvement": 0
        },
        {
            "iteration_id": "0d769cd5-fdf9-4bd5-aa4b-b620431d59c8",
            "iteration_number": 5,
            "approach_description": "Streaming AXIS + ap_ctrl_none + STREAM depth=8 + ARRAY_PARTITION complete + full UNROLL + PIPELINE II=1",
            "ii_achieved": 1,
            "latency_cycles": 9,
            "timing_met": true,
            "resource_usage": "{\"FF\": 4772, \"DSP\": 2, \"LUT\": 2306, \"BRAM_18K\": 0}",
            "created_at": "2025-11-04T14:37:12.043838",
            "ii_improvement": 127
        }
    ]
}
```

**Response field description (per iteration)**:

| Field | Type | Description |
| --- | --- | --- |
| `iteration_id` | UUID | Iteration unique identifier (can be used to query full details including code_snapshot) |
| `iteration_number` | int | Iteration sequence number |
| `approach_description` | string | Optimization approach description |
| `ii_achieved` | int | II achieved |
| `latency_cycles` | int\\|null | Latency in cycles |
| `timing_met` | bool\\|null | Whether timing was met |
| `resource_usage` | string | Resource usage in JSON string format |
| `created_at` | string | Creation time |
| `ii_improvement` | int | II improvement relative to previous iteration (**only present from the 2nd record onward**) |

> `ii_improvement` calculation: `previous iteration's ii_achieved - current iteration's ii_achieved`. The 1st iteration does not have this field.

---

## 2. Dual-Tier Rule System Examples

### 2.1 Rule System Overview

| Tier | Code Range | rule_type Value | source Value | Count | Description |
| --- | --- | --- | --- | --- | --- |
| Official rules | R001–R287 | `official` | `UG1399` | 287 | Vitis HLS UG1399 best practices |
| User-defined | P001–P104 | `user_defined` | `User` | 105 | Practical project optimization experience (extensible) |

> **`rule_type` only supports two values**: `official` and `user_defined`. No other values.

### 2.2 Query Official Rules (R###)

**Scenario**: Before starting FIR optimization, view pipeline-related official rules.

```bash
# Query pipeline category official rules (including never-applied ones)
curl -s "http://localhost:8000/api/rules/effective?rule_type=official&category=pipeline&min_success_rate=0" \
  | python3 -m json.tool
```

**How to interpret the response**:

```
Rule R063 (priority=9, success_rate=1.0, avg_ii_improvement=127.0)
  → High priority, 100% success rate, average improvement 127 cycles
  → Conclusion: strongly recommended for FIR designs

Rule R284 (priority=9, times_applied=0)
  → Never applied, no statistics available
  → Conclusion: can reference but no historical validation
```

### 2.3 Query User-Defined Rules (P###)

**Scenario**: View all user-defined rules and their effectiveness.

```bash
curl -s "http://localhost:8000/api/rules/effective?rule_type=user_defined&min_success_rate=0" \
  | python3 -m json.tool
```

**Key rules from actual response**:

| rule_code | rule_text | success_rate | avg_ii_improvement | Recommendation |
| --- | --- | --- | --- | --- |
| P001 | Always aim for II=1 and full DATAFLOW pipeline. | 1.0 | 130.0 | Apply first |
| P085 | Place PIPELINE II=1 ONLY on main time-step loop... | 1.0 | 126.5 | Essential for systolic designs |
| P002 | Use pure DATAFLOW structure. | 1.0 | 6.0 | Applicable but smaller improvement |
| P003 | Must completely overlap load, compute, and store. | 1.0 | 0.0 | Structural rule, does not directly improve II |

### 2.4 Query High Success Rate Rules (>= 70%, mixed)

**Scenario**: Directly query verified high-effectiveness rules, regardless of official/user_defined.

```bash
curl -s "http://localhost:8000/api/rules/effective?min_success_rate=0.7&project_type=fir" \
  | python3 -m json.tool
```

Results are sorted by `success_rate DESC, priority DESC`, containing a mix of R### and P### rules.

### 2.5 How to Reference Rules in Code

When recording iterations, precisely reference rules in `rules_applied`:

```json
"rules_applied": [
    {
        "rule_code": "P001",
        "rule_description": "Merge related operations into single loops",
        "previous_ii": 264,
        "current_ii": 134,
        "success": true,
        "category": "optimization"
    },
    {
        "rule_code": "R063",
        "rule_description": "Always strive for II=1",
        "previous_ii": 264,
        "current_ii": 134,
        "success": true,
        "category": "pipeline"
    }
]
```

**Rule matching priority**:

1. **`rule_code` exact match** (`WHERE rule_code = 'P001'`) — 100% accurate, preferred
  - Source A: Directly retrieved during Track 2 query
  - Source B: Explicitly specified by user
  - Source C: Extracted from historical code_snapshot header's Applied Rules
2. **Cursor semantic matching of rule_text** — used when Layer 1 yields no results
  - Determine the optimization technique's category → query all rules under that category → LLM semantic matching of rule_text + category dual verification
  - Confident match → take rule_code and fill into rules_applied
  - Cannot confirm → do not fill rules_applied; record in approach_description + code_snapshot Applied Rules as plain text
3. **No match** → that rule is skipped, does not affect other records

---

## 3. Automatic Design Iteration Recording Examples

### 3.1 Complete 5-Step Process (with Actual Commands)

Using the FIR128 project as an example, assuming the 6th synthesis has been completed.

#### Step 1: Parse Synthesis Report

Extract from the HLS synthesis report (`solution1/syn/report/design_csynth.rpt`): `ii_bneck`, `ii_top`, Latency, Timing, Resources (DSP/LUT/FF/BRAM_18K). For detailed parsing format, see the Report Parsing Guidelines in cursorrules.

#### Step 2: Query existing project_id (CRITICAL — MUST DO FIRST)

```bash
# Use /api/projects + project_name exact match to retrieve project_id (recommended approach)
# ❗ Do NOT use /api/design/similar to get project_id — similar sorts by ii_achieved,
#    and when there are multiple projects of the same project_type, results[0] may be from another project
PROJECTS_RESULT=$(curl -s "http://localhost:8000/api/projects?type=fir")

# Exact match by project_name
PROJECT_ID=$(echo "$PROJECTS_RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data['results']:
    if r['name'] == 'FIR128_Demo':
        print(r['id'])
        break
else:
    print('NOT_FOUND')
")

echo "project_id: $PROJECT_ID"
# Expected output: project_id: 550e8400-e29b-41d4-a716-446655440001
# ❗ iteration_number is automatically computed by the complete_iteration API (MAX+1), no local calculation needed
```

> **Warning: If PROJECT_ID = "NOT_FOUND"**, this is a new project; generate a new UUID:
> 
> ```bash
> PROJECT_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
> ```

#### Step 3: Fill User Input Fields

Reference the final values from front-capture (detailed rules in Section 7 "User Input Front-Capture"):

| Field | Source | Description |
| --- | --- | --- |
| `user_reference_code` | USER_REF_CODE (maintained each round) | User's latest reference code to date, semantic judgment for overwrite/append |
| `user_specification` | USER_SPEC (maintained each round) | User's accumulated performance requirements/constraints, semantic judgment for merge/correction |
| `reference_metadata` | Auto-inferred from USER_REF_CODE + parsed report | Language (`{"language":"c"}` / `"cpp"` / `"pseudocode"}`) + `ii_top` + `ii_top_previous` (every iteration); first iteration Layer 2 additionally requires `previous_ii_source` + `previous_ii_basis` |

> ❗ This step directly references the final values from front-capture; no need to scan conversation history again.

#### Step 3a: Identify Applied Rules

Based on pragmas used in the code, bind rule_code by cross-referencing Track 2 query results, and fill into `rules_applied`. Prefer Layer 1 exact binding; when rule_code is unavailable, Cursor performs semantic matching against rule_text (Layer 2). When confident matching is not possible, record in approach_description and code_snapshot header Applied Rules as plain text without filling rules_applied. Applied Rules must also be recorded in the `code_snapshot` header (see cursorrules code_snapshot specification).

#### Step 4: Call complete_iteration API

```bash
curl -X POST "http://localhost:8000/api/design/complete_iteration" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "550e8400-e29b-41d4-a716-446655440001",
    "project_name": "FIR128_Demo",
    "project_type": "fir",
    "target_device": "xc7z020clg400-1",
    "iteration": {
      "project_id": "550e8400-e29b-41d4-a716-446655440001",
      "approach_description": "Streaming AXIS + complete partition + full unroll + PIPELINE II=1",
      "code_snapshot": "// ============================================================================\n// FIR128_Demo - Iteration #6: Further optimization\n// ...\nvoid FIR(hls::stream<data_t> &s_in, hls::stream<data_t> &s_out) {\n    // ... complete code ...\n}\n",
      "pragmas_used": [
        "#pragma HLS ARRAY_PARTITION variable=shift_reg complete dim=1",
        "#pragma HLS PIPELINE II=1",
        "#pragma HLS UNROLL"
      ],
      "prompt_used": "Optimize the FIR design to achieve II=1",
      "cursor_reasoning": "Based on Iteration #5's success, maintaining complete partition + full unroll architecture. ii_bneck: 128→1; ii_top: 517→517; rules_applied success basis: ii_bneck only (Layer A).",
      "user_reference_code": null,
      "user_specification": "Target II=1, DSP<=2",
      "reference_metadata": {"has_specification": true, "ii_top": 517, "ii_top_previous": 517}
    },
    "synthesis_result": {
      "ii_achieved": 1,
      "ii_target": 1,
      "latency_cycles": 9,
      "timing_met": true,
      "resource_usage": {"DSP": 2, "LUT": 2306, "FF": 4772, "BRAM_18K": 0},
      "clock_period_ns": 10.0
    },
    "rules_applied": [
      {
        "rule_code": "P001",
        "rule_description": "Always aim for II=1",
        "previous_ii": 128,
        "current_ii": 1,
        "success": true,
        "category": "optimization"
      },
      {
        "rule_code": "R035",
        "rule_description": "Pipeline innermost loop",
        "previous_ii": 128,
        "current_ii": 1,
        "success": true,
        "category": "pipeline"
      }
    ]
  }'
```

**Expected response**:

```json
{
    "status": "success",
    "iteration_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "iteration_number": 6,
    "project_id": "550e8400-e29b-41d4-a716-446655440001",
    "rules_recorded": 2,
    "message": "Complete iteration record created (iteration #6, 2 rule effectiveness record(s) updated)"
}
```

**Verification**:

- ✓ `iteration_number` = 6 (previous was 5, correctly incremented)
- ✓ `project_id` = `550e8400-...` (matches the query result)
- ✓ `rules_recorded` = 2 (both rules matched successfully)

> **Warning: If `iteration_number` = 1**: An incorrect `project_id` was used, causing the API to treat it as a new project. Stop immediately and go back to Step 0 to re-query.

#### Step 5: Document Locally

Even if the API call succeeds, **local documentation must still be created** (`optimization_summary.md`, `performance_comparison.txt`, etc.). Local documentation is the only backup when the API is unavailable; for format specifications, see the Local Documentation Template in cursorrules.

### 3.2 Handling API Failures

```
API returns 500 Internal Server Error
  ↓
✓ Wait 3 seconds and retry once (re-query project_id at Step 0 before retrying)
✗ Do not try with a different project_id
  ↓
Still failing → stop
✓ Ensure local documentation is complete (Step 5)
✓ Inform user: "Results have been recorded in local documentation"
✓ Continue to next iteration
```

---

## 4. End-to-End Complete Workflow

Using **creating a new MatMul project** as an example, demonstrating the complete workflow from scratch.

### Phase 1: Query Phase (Pre-Design)

```bash
# Track 1: Query similar designs (sorted by ii_achieved ascending, understand performance ceiling)
curl -s "http://localhost:8000/api/design/similar?project_type=matmul&limit=10" \
  | python3 -m json.tool

# Track 2 Path A (when similar projects exist): Query rules by inferred category; Cursor handles semantic filtering and statistical sort
curl -s "http://localhost:8000/api/rules/effective?category=memory&min_success_rate=0" \
  | python3 -m json.tool

# Track 2 Path B (no similar projects): Retrieve all rules, Cursor filters by times_applied / priority
curl -s "http://localhost:8000/api/rules/effective?category=pipeline&min_success_rate=0" \
  | python3 -m json.tool
```

### Phase 2: Design and Synthesis

```bash
# Create project directory
mkdir -p ~/matmul_project && cd ~/matmul_project

# Write HLS code (with complete comments, following Code Snapshot Comment Standards)
# Write testbench
# Generate run_hls.tcl

# Execute synthesis
source /opt/Xilinx/Vitis_HLS/2022.1/settings64.sh
vitis_hls -f run_hls.tcl
```

### Phase 3: Recording Phase

```bash
# Step 2: Use /api/projects + project_name exact match to retrieve project_id
# ❗ Do NOT use /api/design/similar to get project_id — similar sorts by ii_achieved,
#    and when there are multiple projects of the same project_type, results[0] may be from another project
PROJECT_NAME="MatMul_4x4_Demo"
PROJECT_TYPE="matmul"
PROJECT_ID=$(curl -s "http://localhost:8000/api/projects?type=${PROJECT_TYPE}" | \
  python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data['results']:
    if r['name'] == '${PROJECT_NAME}':
        print(r['id'])
        break
else:
    import uuid
    print(uuid.uuid4())  # New project
")

# Main flow step 10: Call complete_iteration (Record to KB)
curl -X POST "http://localhost:8000/api/design/complete_iteration" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "project_name": "MatMul_4x4_Demo",
    "project_type": "matmul",
    "iteration": { ... },
    "synthesis_result": { ... },
    "rules_applied": [ ... ]
  }'

# Main flow step 11: Document Local (Create local documentation)
# (Create README.md, optimization_summary.md, performance_comparison.txt)
```

### Phase 4: Verification and Follow-up

```bash
# Verify record
curl -s "http://localhost:8000/api/design/similar?project_type=matmul&limit=5" | python3 -m json.tool

# View project progress
curl -s "http://localhost:8000/api/analytics/project/${PROJECT_ID}/progress" | python3 -m json.tool
```

---

## Troubleshooting

### 1. API Returns Empty Results

| Symptom | Possible Cause | Solution |
| --- | --- | --- |
| `results: []` | `project_type` misspelling | Confirm using lowercase (`fir` not `FIR`) |
| `results: []` | `target_ii` set too low | Remove `target_ii` parameter; view all first |
| `rules: []` | `min_success_rate` too high | Set to `0` to view all |
| `rules: []` | `rule_type` value incorrect | Only supports `official` or `user_defined` |

### 2. rules_recorded=0 (Expected Rule Matches)

**Cause**: `rule_code` misspelling, or semantic matching could not find a corresponding rule.

**Troubleshooting steps**:

```bash
# Confirm rule_code exists
curl -s "http://localhost:8000/api/rules/effective?min_success_rate=0" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
codes = [r['rule_code'] for r in data['rules']]
print('Available codes:', sorted(set(codes))[:20])
"
```

### 3. resource_usage Is a String Not an Object

**Symptom**: `"resource_usage": "{\"DSP\": 2, \"LUT\": 348}"`

**Cause**: Stored as a JSON string in the database; the API returns it without deserialization.

**Handling**:

```python
import json
resource = json.loads(result['resource_usage'])
print(f"DSP: {resource['DSP']}, LUT: {resource['LUT']}")
```

```bash
# Or use jq
echo '"{\"DSP\": 2}"' | jq -r '. | fromjson'
```

---

> **Version**: v1.0
> **Last Updated**: 2026-03-28