#!/bin/bash
# Copyright (c) 2026 AICOFORGE. All rights reserved.
# CC BY-NC 4.0 — non-commercial use only. See LICENSE.
# Commercial use: kevinjan@aicoforge.com

# ============================================================================
# generate-mdc.sh
# Generate .cursor/rules/*.mdc from 3 .mdc-template files + hls-env.conf
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/hls-env.conf"
RULES_DIR="${SCRIPT_DIR}/.cursor/rules"

# --- Template / Output pairs ---
TEMPLATE_NAMES=(
    "hls-core.mdc-template"
    "hls-code-standards.mdc-template"
    "hls-recording.mdc-template"
)
OUTPUT_NAMES=(
    "hls-core.mdc"
    "hls-code-standards.mdc"
    "hls-recording.mdc"
)

# --- Check environment config ---
if [ ! -f "$ENV_FILE" ]; then
    echo "✗ Environment config file not found: $ENV_FILE"
    exit 1
fi

# --- Check all templates ---
for name in "${TEMPLATE_NAMES[@]}"; do
    if [ ! -f "${SCRIPT_DIR}/${name}" ]; then
        echo "✗ Template file not found: ${SCRIPT_DIR}/${name}"
        exit 1
    fi
done

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  generate-mdc.sh                                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# --- Read KEY=VALUE pairs (handles files with or without trailing newline) ---
while IFS= read -r line || [ -n "$line" ]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" =~ ^[A-Z_]+=.+ ]]; then
        export "$line"
    fi
done < "$ENV_FILE"

# --- Detect current environment ---
GEN_HOSTNAME=$(hostname)
GEN_IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}')

# Check if Vitis HLS is installed
if [ -f "${VITIS_HLS_SETTING_PATH}" ]; then
    source "${VITIS_HLS_SETTING_PATH}" 2>/dev/null
    _vitis_bin=$(which "${VITIS_HLS_CMD}" 2>/dev/null || echo "")
    if [ -n "$_vitis_bin" ] && [ -x "$_vitis_bin" ]; then
        GEN_HAS_VITIS="$_vitis_bin"
        GEN_VITIS_STATUS="✓ Installed (${GEN_HAS_VITIS})"
    else
        GEN_HAS_VITIS=""
        GEN_VITIS_STATUS="✗ Not installed"
    fi
else
    GEN_HAS_VITIS=""
    GEN_VITIS_STATUS="✗ Not installed"
fi

# --- Check network segment compatibility ---
if [ -n "$GEN_IP_ADDR" ] && [ -n "$KB_HOST_IP" ]; then
    _local_subnet=$(echo "$GEN_IP_ADDR" | cut -d'.' -f1-3)
    _kb_subnet=$(echo "$KB_HOST_IP"    | cut -d'.' -f1-3)
    if [ "$_local_subnet" != "$_kb_subnet" ]; then
        echo "╔══════════════════════════════════════════════════════════╗"
        echo "║  X  NETWORK SEGMENT MISMATCH — CANNOT REACH KB HOST      ║"
        echo "╚══════════════════════════════════════════════════════════╝"
        echo ""
        echo "  Local host : ${GEN_HOSTNAME} (${GEN_IP_ADDR})  → subnet ${_local_subnet}.0/24"
        echo "  KB host    : ${KB_HOST_NAME} (${KB_HOST_IP})  → subnet ${_kb_subnet}.0/24"
        echo ""
        echo "  The KB API at http://${KB_HOST_IP}:${KB_API_PORT} is likely"
        echo "  unreachable from this machine."
        echo ""
        exit 1
    fi
fi

# --- Decide KB API URL ---
if [ "$GEN_HOSTNAME" = "$KB_HOST_NAME" ] || [ "$GEN_IP_ADDR" = "$KB_HOST_IP" ]; then
    GEN_KB_API="http://localhost:${KB_API_PORT}"
else
    GEN_KB_API="http://${KB_HOST_IP}:${KB_API_PORT}"
fi

# --- Compute derived variables ---
KB_API_URL_LOCAL="http://localhost:${KB_API_PORT}"
KB_API_URL_REMOTE="http://${KB_HOST_IP}:${KB_API_PORT}"
DB_URL_LOCAL="postgresql://${DB_USER}:${DB_PASS}@localhost:${DB_PORT}/${DB_NAME}"
DB_URL_REMOTE="postgresql://${DB_USER}:${DB_PASS}@${KB_HOST_IP}:${DB_PORT}/${DB_NAME}"

echo "KB Host:     ${KB_HOST_NAME} (${KB_HOST_IP})"
echo ""
echo "--- Current Environment ---"
echo "Hostname:    $GEN_HOSTNAME"
echo "IP Address:  $GEN_IP_ADDR"
echo "Vitis HLS:   $GEN_VITIS_STATUS"
echo "KB API:      $GEN_KB_API"
echo ""

# --- Create output directory ---
mkdir -p "$RULES_DIR"
echo "Output dir:  $RULES_DIR"
echo ""

# --- Variable substitution table ---
declare -A VARS=(
    ["{{KB_HOST_NAME}}"]="$KB_HOST_NAME"
    ["{{KB_HOST_IP}}"]="$KB_HOST_IP"
    ["{{KB_API_PORT}}"]="$KB_API_PORT"
    ["{{KB_API_URL_LOCAL}}"]="$KB_API_URL_LOCAL"
    ["{{KB_API_URL_REMOTE}}"]="$KB_API_URL_REMOTE"
    ["{{DB_USER}}"]="$DB_USER"
    ["{{DB_PASS}}"]="$DB_PASS"
    ["{{DB_NAME}}"]="$DB_NAME"
    ["{{DB_PORT}}"]="$DB_PORT"
    ["{{DB_URL_LOCAL}}"]="$DB_URL_LOCAL"
    ["{{DB_URL_REMOTE}}"]="$DB_URL_REMOTE"
    ["{{VITIS_HLS_SETTING_PATH}}"]="$VITIS_HLS_SETTING_PATH"
    ["{{VITIS_HLS_CMD}}"]="$VITIS_HLS_CMD"
    ["{{TARGET_PART}}"]="$TARGET_PART"
    ["{{DEFAULT_CLOCK_PERIOD_NS}}"]="$DEFAULT_CLOCK_PERIOD_NS"
    ["{{GEN_HOSTNAME}}"]="$GEN_HOSTNAME"
    ["{{GEN_IP_ADDR}}"]="$GEN_IP_ADDR"
    ["{{GEN_VITIS_STATUS}}"]="$GEN_VITIS_STATUS"
    ["{{GEN_KB_API}}"]="$GEN_KB_API"
)

# --- Process each template ---
TOTAL_REMAINING=0

for i in "${!TEMPLATE_NAMES[@]}"; do
    TEMPLATE_FILE="${SCRIPT_DIR}/${TEMPLATE_NAMES[$i]}"
    OUTPUT_FILE="${RULES_DIR}/${OUTPUT_NAMES[$i]}"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Processing: ${TEMPLATE_NAMES[$i]}"
    echo "  → ${OUTPUT_FILE}"

    cp "$TEMPLATE_FILE" "$OUTPUT_FILE"

    for key in "${!VARS[@]}"; do
        val="${VARS[$key]}"
        n=$(grep -c "$key" "$OUTPUT_FILE" 2>/dev/null || true)
        if [ "$n" -gt 0 ]; then
            python3 -c "
import sys
with open('${OUTPUT_FILE}', 'r') as f:
    c = f.read()
c = c.replace('${key}', '''${val}''')
with open('${OUTPUT_FILE}', 'w') as f:
    f.write(c)
"
            echo "  ✓ ${key} → ${val} (${n} occurrence(s))"
        fi
    done

    # Verify no remaining placeholders
    remaining=$(grep -c '{{[A-Z_]*}}' "$OUTPUT_FILE" 2>/dev/null || true)
    total_lines=$(wc -l < "$OUTPUT_FILE")
    TOTAL_REMAINING=$((TOTAL_REMAINING + remaining))

    if [ "$remaining" -eq 0 ]; then
        echo "  ✓ Substitution complete (${total_lines} lines)"
    else
        echo "  ❗  ${remaining} unresolved variable(s) remaining:"
        grep -n '{{[A-Z_]*}}' "$OUTPUT_FILE" | head -10
    fi
    echo ""
done

# --- Summary ---
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Generated files:"
for i in "${!OUTPUT_NAMES[@]}"; do
    OUTPUT_FILE="${RULES_DIR}/${OUTPUT_NAMES[$i]}"
    lines=$(wc -l < "$OUTPUT_FILE")
    size=$(du -h "$OUTPUT_FILE" | awk '{print $1}')
    printf "  %-40s %5d lines  %s\n" "${OUTPUT_NAMES[$i]}" "$lines" "$size"
done
echo ""

if [ "$TOTAL_REMAINING" -eq 0 ]; then
    echo "✓ All done! No remaining {{variables}}"
else
    echo "❗  ${TOTAL_REMAINING} unresolved variable(s) total — see output above"
fi
echo ""
echo "Cursor rules directory: ${RULES_DIR}"
echo "✓ Done!"